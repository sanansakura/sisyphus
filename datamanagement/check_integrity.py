import sys
import logging
import click
from dbclients.tantalus import TantalusApi, DataCorruptionError, DataMissingError
from dbclients.basicclient import NotFoundError
from utils.constants import LOGGING_FORMAT


logging.basicConfig(format=LOGGING_FORMAT, stream=sys.stderr, level=logging.INFO)
logging.getLogger('azure.storage').setLevel(logging.ERROR)


def get_dataset_file_instances(tantalus_api, dataset_type, dataset_id=None, tag_name=None):
    if dataset_type is None:
        raise ValueError('require dataset type')

    if dataset_id is not None and tag_name is not None:
        raise ValueError('require at most one of dataset id or tag name')

    if dataset_id is not None:
        logging.info('check dataset {}, {}'.format(dataset_id, dataset_type))
        datasets = tantalus_api.list(dataset_type, id=dataset_id)

    elif tag_name is not None:
        logging.info('check tag {}'.format(tag_name))
        datasets = tantalus_api.list(dataset_type, tags__name=tag_name)

    else:
        logging.info('check all datasets of type {}'.format(dataset_type))
        datasets = tantalus_api.list(dataset_type)

    for dataset in datasets:
        logging.info('checking dataset with id {}, name {}'.format(
            dataset['id'], dataset['name']))

        for file_resource in tantalus_api.get_dataset_file_resources(dataset['id'], dataset_type):
            yield file_resource


@click.command()
@click.argument('storage_name')
@click.option('--dataset_type')
@click.option('--dataset_id', type=int)
@click.option('--tag_name')
@click.option('--all_file_instances', is_flag=True)
@click.option('--dry_run', is_flag=True)
@click.option('--fix_corrupt', is_flag=True)
@click.option('--remove_missing', is_flag=True)
def main(
        storage_name,
        dataset_type=None,
        dataset_id=None,
        tag_name=None,
        all_file_instances=False,
        dry_run=False,
        fix_corrupt=False,
        remove_missing=False,
    ):
    logging.info('checking integrity of storage {}'.format(storage_name))

    tantalus_api = TantalusApi()

    if all_file_instances:
        file_resources = tantalus_api.list('file_resource', fileinstance__storage__name=storage_name)

    else:
        file_resources = get_dataset_file_instances(
            tantalus_api, dataset_type, dataset_id=dataset_id, tag_name=tag_name)

    for file_resource in file_resources:
        try:
            file_instance = tantalus_api.get('file_instance', file_resource=file_resource['id'], storage__name=storage_name)
        except NotFoundError:
            logging.exception(f'file {file_resource["filename"]} not on storage')
            continue

        logging.info('checking file instance {} with path {}'.format(
            file_instance['id'], file_instance['filepath']))

        if file_instance['is_deleted']:
            logging.info('file instance {} marked as deleted'.format(
                file_instance['id']))
            continue

        file_corrupt = False
        file_missing = False
        try:
            tantalus_api.check_file(file_instance)
        except DataCorruptionError:
            file_corrupt = True
            logging.exception('check file failed')
        except DataMissingError:
            file_missing = True
            logging.exception('missing file')

        if file_corrupt and fix_corrupt:
            logging.info('updating file instance {} with path {}'.format(
                file_instance['id'], file_instance['filepath']))

            if not dry_run:
                tantalus_api.update_file(file_instance)

        if file_missing and remove_missing:
            logging.info('deleting file instance {} with path {}'.format(
                file_instance['id'], file_instance['filepath']))

            if not dry_run:
                file_instance = tantalus_api.update(
                    'file_instance',
                    id=file_instance['id'],
                    is_deleted=True,
                )


if __name__ == "__main__":
    main()

