import os
import datamanagement.templates as templates
import dbclients.tantalus

tantalus_api = dbclients.tantalus.TantalusApi()


def check_gsc_lane_id(lane_id):
    if not templates.LANE_ID_RE.match(lane_id):
        raise Exception("Invalid GSC lane {}".format(lane_id))


def sequence_dataset_match_lanes(dataset, lane_ids):
    if lane_ids is None:
        return True

    dataset_lanes = get_lanes_from_dataset(dataset)
    return set(lane_ids) == set(dataset_lanes)


def get_flowcell_lane(lane):
    if lane['lane_number'] == '':
        return lane['flowcell_id']
    else:
        return '{}_{}'.format(lane['flowcell_id'], lane['lane_number'])


def get_lanes_from_dataset(dataset):
    """
    Return a list of lanes given a dataset, where each lane has the format
    [flowcell_id]_[lane_number].
    Args:
        dataset (dict)
    Returns:
        lanes (list)
    """
    lanes = set()
    for lane in dataset['sequence_lanes']:
        lanes.add(get_flowcell_lane(lane))
    return lanes


def get_sequencing_centre_from_dataset(dataset):
    """
    Return a sequencing centre (e.g. GSC, BRC) given a dataset.
    An error is thrown if more than one sequencing centre is found.
    Args:
        dataset (dict)
    Returns:
        sequencing_centre (str)
    """

    sequencing_centres = {lane['sequencing_centre'] for lane in dataset['sequence_lanes']}

    if len(sequencing_centres) != 1:
        raise Exception('{} sequencing centers found for dataset {}'.format(
            len(sequencing_centres),
            dataset['id'])
        )

    return list(sequencing_centres).pop()


def get_sequencing_instrument_from_dataset(dataset):
    """
    Return a sequencing instrument given a dataset.
    An error is thrown if more than one sequencing instrument is found.
    Args:
        dataset (dict)
    Returns:
        sequencing_instrument (str)
    """

    sequencing_instruments = {lane['sequencing_instrument'] for lane in dataset['sequence_lanes']}

    if len(sequencing_instruments) != 1:
        raise Exception('{} sequencing instruments found for dataset {}'.format(
            len(sequencing_instruments),
            dataset['id'])
        )

    return list(sequencing_instruments).pop()


def get_storage_type(storage_name):
    """
    Return the storage type of a storage with a given name
    Args:
        storage_name (string)
    Returns:
        storage_type (string)
    """

    storage = tantalus_api.get_storage(storage_name)
    
    return storage['storage_type']




