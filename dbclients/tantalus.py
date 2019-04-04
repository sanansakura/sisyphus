"""Contains a Tantalus API class to make requests to Tantalus.

This class makes no attempt at being all-encompassing. It covers a
subset of Tantalus API features to meet the needs of the automation
scripts.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import json
import os
import time
import datetime
import logging
import shutil
import pandas as pd

try:
    from urllib.request import urlopen
except ImportError:
    from urllib2 import urlopen

from datamanagement.utils.django_json_encoder import DjangoJSONEncoder
from dbclients.basicclient import BasicAPIClient, FieldMismatchError, NotFoundError

import azure.storage.blob
from azure.keyvault import KeyVaultClient, KeyVaultAuthentication
from azure.common.credentials import ServicePrincipalCredentials


log = logging.getLogger('sisyphus')

TANTALUS_API_URL = "https://tantalus.canadacentral.cloudapp.azure.com/api/"


def get_storage_account_key(
        accountname, client_id, secret_key, tenant_id, keyvault_account
):
    def auth_callback(server, resource, scope):
        credentials = ServicePrincipalCredentials(
            client_id=client_id,
            secret=secret_key,
            tenant=tenant_id,
            resource="https://vault.azure.net"
        )
        token = credentials.token
        return token['token_type'], token['access_token']

    client = KeyVaultClient(KeyVaultAuthentication(auth_callback))
    keyvault = "https://{}.vault.azure.net/".format(keyvault_account)

    # passing in empty string for version returns latest key
    secret_bundle = client.get_secret(keyvault, accountname, "")
    return secret_bundle.value


class BlobStorageClient(object):
    def __init__(self, storage_account, storage_container, prefix):
        self.storage_account = storage_account
        self.storage_container = storage_container
        self.prefix = prefix

        client_id = os.environ["CLIENT_ID"]
        secret_key = os.environ["SECRET_KEY"]
        tenant_id = os.environ["TENANT_ID"]
        keyvault_account = os.environ['AZURE_KEYVAULT_ACCOUNT']

        storage_key = get_storage_account_key(
            self.storage_account, client_id, secret_key,
            tenant_id, keyvault_account)

        self.blob_service = azure.storage.blob.BlockBlobService(
            account_name=self.storage_account,
            account_key=storage_key)
        self.blob_service.MAX_BLOCK_SIZE = 64 * 1024 * 1024

    def get_size(self, blobname):
        properties = self.blob_service.get_blob_properties(self.storage_container, blobname)
        blobsize = properties.properties.content_length
        return blobsize

    def get_created_time(self, blobname):
        properties = self.blob_service.get_blob_properties(self.storage_container, blobname)
        created_time = properties.properties.last_modified.isoformat()
        return created_time

    def get_url(self, blobname):
        sas_token = self.blob_service.generate_blob_shared_access_signature(
            self.storage_container,
            blobname,
            permission=azure.storage.blob.BlobPermissions.READ,
            expiry=datetime.datetime.utcnow() + datetime.timedelta(hours=12),
        )
        blob_url = self.blob_service.make_blob_url(
            container_name=self.storage_container,
            blob_name=blobname,
            protocol="https",
            sas_token=sas_token,
        )
        blob_url = blob_url.replace(' ', '%20')
        return blob_url

    def delete(self, blobname):
        self.blob_service.delete_blob(self.storage_container, blob_name=blobname)

    def open_file(self, blobname):
        url = self.get_url(blobname)
        return urlopen(url)

    def exists(self, blobname):
        return self.blob_service.exists(self.storage_container, blob_name=blobname)

    def list(self, prefix):
        for blob in self.blob_service.list_blobs(self.storage_container, prefix=prefix):
            yield blob.name

    def write_data(self, blobname, stream):
        stream.seek(0)
        return self.blob_service.create_blob_from_stream(
            self.storage_container,
            blob_name=blobname,
            stream=stream)
        
    def create(self, blobname, filepath):
        if self.exists(blobname):
            filesize_on_azure = self.get_size(blobname)
            filesize = os.path.getsize(filepath)

            if filesize_on_azure != filesize:
                raise Exception("Size mismatch: {} on Azure but file has size {}".format(filesize_on_azure, filesize))

            log.info("{} already exists on {}/{}".format(blobname, self.storage_account, self.storage_container))

        else:
            log.info("Creating blob {} from path {}".format(blobname, filepath))
            self.blob_service.create_blob_from_path(self.storage_container, 
                blobname,
                filepath)
            
class ServerStorageClient(object):
    def __init__(self, storage_directory, prefix):
        self.storage_directory = storage_directory
        self.prefix = prefix

    def get_size(self, filename):
        filepath = os.path.join(self.storage_directory, filename)
        return os.path.getsize(filepath)

    def get_created_time(self, filename):
        filepath = os.path.join(self.storage_directory, filename)
        # TODO: this is currently fixed at pacific time
        return pd.Timestamp(time.ctime(os.path.getmtime(filepath)), tz="Canada/Pacific").isoformat()

    def get_url(self, filename):
        filepath = os.path.join(self.storage_directory, filename)
        return filepath

    def delete(self, filename):
        os.remove(self.get_url(filename))

    def open_file(self, filename):
        filepath = os.path.join(self.storage_directory, filename)
        return open(filepath)

    def exists(self, filename):
        filepath = os.path.join(self.storage_directory, filename)
        return os.path.exists(filepath)

    def list(self, prefix):
        for root, dirs, files in os.walk(os.path.join(self.storage_directory, prefix)):
            for filename in files:
                yield os.path.join(root, filename)

    def write_data(self, filename, stream):
        stream.seek(0)
        filepath = os.path.join(self.storage_directory, filename)
        dirname = os.path.dirname(filepath)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
            
        with open(filepath, "wb") as f:
            f.write(stream.getvalue())

    def create(self, filename, filepath):
        tantalus_filepath = os.path.join(self.storage_directory, filename)
        if not os.path.samefile(filepath, tantalus_filepath):
            shutil.copy(filepath, tantalus_filepath)


class DataCorruptionError(Exception):
    """ An error when missing or corrupt data is found.
    """
    pass


class TantalusApi(BasicAPIClient):
    """Tantalus API class."""

    # Parameters used for pagination
    pagination_param_names = ("limit", "offset")

    def __init__(self):
        """Set up authentication using basic authentication.

        Expects to find valid environment variables
        TANTALUS_API_USERNAME and TANTALUS_API_PASSWORD. Also looks for
        an optional TANTALUS_API_URL.
        """

        super(TantalusApi, self).__init__(
            os.environ.get("TANTALUS_API_URL", TANTALUS_API_URL),
            username=os.environ.get("TANTALUS_API_USERNAME"),
            password=os.environ.get("TANTALUS_API_PASSWORD"),
        )

        self.cached_storages = {}
        self.cached_storage_clients = {}

    def get_list_pagination_initial_params(self, params):
        """Get initial pagination parameters specific to this API.

        For example, offset and limit for offset/limit pagination.

        Args:
            params: A dict which is changed in place.
        """
        params["limit"] = 100
        params["offset"] = 0

    def get_list_pagination_next_page_params(self, params):
        """Get next page pagination parameters specific to this API.

        For example, offset and limit for offset/limit pagination.

        Args:
            params: A dict which is changed in place.
        """
        params["offset"] += params["limit"]

    def get_file_resource_filename(self, storage_name, filepath):
        """ Strip the storage directory from a filepath to create a tantalus filename.

        Args:
            storage_name: storage in which the file resides
            filepath: abs path of the file
        
        Returns:
            filename: relative filename of the file
        """
        storage = self.get_storage(storage_name)

        if not filepath.startswith(storage['prefix']):
            raise ValueError('file {} not in storage {} with prefix {}'.format(
                filepath, storage['name'], storage['prefix']))

        filename = filepath[len(storage['prefix']):]
        filename = filename.lstrip('/')

        return filename

    def get_filepath(self, storage_name, filename):
        """ Prefix the filename with the storage prefix to create a full filepath.

        Args:
            storage_name: storage in which the file resides
            filename: relative filename of the file
        
        Returns:
            filepath: abs path of the file
        """
        storage = self.get_storage(storage_name)
        
        if filename.startswith('/') or '..' in filename:
            raise ValueError('expected relative path got {}'.format(filename))

        return os.path.join(storage['prefix'], filename)

    def get_storage(self, storage_name):
        """ Retrieve a storage object with caching.

        Args:
            storage_name: storage in which the file resides

        Returns:
            storage details (dict)
        """
        if storage_name in self.cached_storages:
            return self.cached_storages[storage_name]

        storage = self.get('storage', name=storage_name)

        self.cached_storages[storage_name] = storage

        return storage

    def get_cache_client(self, storage_directory):
        """ Retrieve a client for the given cache

        Args:
            storage_directory: directory in which the files are cached

        Returns:
            storage client object
        """
        return ServerStorageClient(storage_directory, storage_directory)

    def get_storage_client(self, storage_name):
        """ Retrieve a client for the given storage

        Args:
            storage_name: storage in which the file resides

        Returns:
            storage client object
        """
        if storage_name in self.cached_storage_clients:
            return self.cached_storage_clients[storage_name]

        storage = self.get_storage(storage_name)

        if storage['storage_type'] == 'blob':
            client = BlobStorageClient(storage['storage_account'], storage['storage_container'], storage['prefix'])
        elif storage['storage_type'] == 'server':
            client = ServerStorageClient(storage['storage_directory'], storage['prefix'])
        else:
            return ValueError('unsupported storage type {}'.format(storage['storage_type']))

        self.cached_storage_clients[storage_name] = client

        return client

    def add_file(self, storage_name, filepath, update=False):
        """ Create a file resource and file instance in the given storage.

        Args:
            storage_name: storage for file instance
            filepath: full path to file

        Kwargs:
            update: update the file if exists

        Returns:
            file_resource, file_instance

        For a file that does not exist, create the file resource and
        file instance on the specific storage and return them.

        If the file already exist in tantalus and the file being
        added has the same properties, add_file will ensure an instance
        exists on the given storage.

        If the file already exists in tantalus and the file being added
        has different properties, functionality will depend on the
        update kwarg.  If update=False, fail with FieldMismatchError.
        If update=True, update the file resource, create a file instance
        on the given storage, and set all other file instances to
        is_delete=True.
        """
        storage = self.get_storage(storage_name)
        storage_client = self.get_storage_client(storage_name)

        log.info('adding file with path {} in storage {}'.format(
            filepath, storage_name))

        filename = self.get_file_resource_filename(storage_name, filepath)

        # Try getting or creating the file resource, will
        # fail if exists with different properties.
        try:
            file_resource = self.get_or_create(
                'file_resource',
                filename=filename,
                created=storage_client.get_created_time(filename),
                size=storage_client.get_size(filename),
            )
            log.info('file resource has id {}'.format(file_resource['id']))
        except FieldMismatchError:
            if not update:
                log.exception('file resource with filename has different properties, not updating'.format(
                    filename))
                raise
            file_resource = None

        # Creating a file did not succeed because it existed but with
        # different properties.  Update the file.
        if file_resource is None:

            # Should have raised above if update=False
            assert update

            # Get existing file resource with different properties
            file_resource = self.get(
                'file_resource',
                filename=filename,
            )
            log.info('updating file resource {}'.format(
                file_resource['id']))

            # Delete all existing instances
            for file_instance in file_resource['file_instances']:
                file_instance = self.update(
                    'file_instance',
                    id=file_instance['id'],
                    is_deleted=True,
                )
                log.info('deleted file instance {}'.format(
                    file_instance['id']))

            # Update the file properties
            file_resource = self.update(
                'file_resource',
                id=file_resource['id'],
                filename=filename,
                created=storage_client.get_created_time(filename),
                size=storage_client.get_size(filename),
            )

        file_instance = self.add_instance(file_resource, storage)

        return file_resource, file_instance

    def update_file(self, file_instance):
        """
        Update a file resource to match the file pointed
        to by the given file instance.

        Args:
            file_instance (dict)

        Returns:
            file_instance (dict)
        """
        storage_client = self.get_storage_client(file_instance['storage']['name'])

        file_resource = self.update(
            'file_resource',
            id=file_instance['file_resource']['id'],
            created=storage_client.get_created_time(file_instance['file_resource']['filename']),
            size=storage_client.get_size(file_instance['file_resource']['filename']),
        )

        file_instance['file_resource'] = file_resource

        return file_instance

    def check_file(self, file_instance):
        """
        Check a file instance in tantalus exists and has the same size
        on its given storage.

        Args:
            file_instance (dict)

        Raises:
            DataCorruptionError
        """
        storage_client = self.get_storage_client(file_instance['storage']['name'])

        if not storage_client.exists(file_instance['file_resource']['filename']):
            raise DataCorruptionError('file instance {} with path {} doesnt exist on storage {}'.format(
                file_instance['id'], file_instance['filepath'], file_instance['storage']['name']))

        size = storage_client.get_size(file_instance['file_resource']['filename'])
        if size != file_instance['file_resource']['size']:
            raise DataCorruptionError('file instance {} with path {} has size {} on storage {} but {} in tantalus'.format(
                file_instance['id'], file_instance['filepath'], size, file_instance['storage']['name'],
                file_instance['file_resource']['size']))

    def add_instance(self, file_resource, storage):
        """
        Add a file instance accounting for the possibility that we are replacing a deleted instance.

        Args:
            file_resource (dict)
            storage (dict)

        Returns:
            file_instance (dict)
        """

        file_instance = self.get_or_create(
            'file_instance',
            file_resource=file_resource['id'],
            storage=storage['id'],
        )

        if file_instance['is_deleted']:
            file_instance = self.update(
                'file_instance',
                id=file_instance['id'],
                is_deleted=False,
            )

        return file_instance

    def get_file_instance(self, file_resource, storage_name):
        """
        Given a file resource and a storage name, return the matching file instance.

        Args:
            file_resource (dict)
            storage_name (str)

        Returns:
            file_instance (dict)
        """
        for file_instance in file_resource['file_instances']:
            if file_instance['storage']['name'] == storage_name:
                file_instance = file_instance.copy()
                file_instance['file_resource'] = file_resource
                return file_instance

        raise NotFoundError

    def get_dataset_file_instances(self, dataset_id, dataset_model, storage_name, filters=None):
        """
        Given a dataset get all file instances.

        Note: file_resource and sequence_dataset are added as fields
        to the file_instances

        Args:
            dataset_id (int): primary key of sequencedataset or resultsdataset
            dataset_model (str): model type, sequencedataset or resultsdataset
            storage_name (str): name of the storage for which to retrieve file instances

        KwArgs:
            filters (dict): additional filters such as filename extension

        Returns:
            file_instances (list)
        """
        if filters is None:
            filters = {}

        file_instances = []

        if dataset_model == 'sequencedataset':
            file_resources = self.list('file_resource', sequencedataset__id=dataset_id, **filters)

        elif dataset_model == 'resultsdataset':
            file_resources = self.list('file_resource', resultsdataset__id=dataset_id, **filters)

        else:
            raise ValueError('unrecognized dataset model {}'.format(dataset_model))

        for file_resource in file_resources:

            file_instance = self.get_file_instance(file_resource, storage_name)
            file_instance['file_resource'] = file_resource

            file_instances.append(file_instance)

        return file_instances

    def get_dataset_file_resources(self, dataset_id, dataset_model, filters=None):
        """
        Given a dataset get all file resources.

        Args:
            dataset_id (int): primary key of sequencedataset or resultsdataset
            dataset_model (str): model type, sequencedataset or resultsdataset

        KwArgs:
            filters (dict): additional filters such as filename extension

        Returns:
            file_resources (list)
        """

        if dataset_model == 'sequencedataset':
            file_resources = self.list('file_resource', sequencedataset__id=dataset_id, **filters)

        elif dataset_model == 'resultsdataset':
            file_resources = self.list('file_resource', resultsdataset__id=dataset_id, **filters)

        else:
            raise ValueError('unrecognized dataset model {}'.format(dataset_model))

        return file_resources

    def is_sequence_dataset_on_storage(self, dataset, storage_name):
        """
        Given a dataset test if all files are on a specific storage.

        Args:
            dataset (dict)
            storage_name (str)

        Returns:
            bool
        """
        for file_resource in self.list('file_resource', sequencedataset__id=dataset['id']):
            try:
                self.get_file_instance(file_resource, storage_name)
            except NotFoundError:
                return False

        return True

    def tag(self, name, sequencedataset_set=(), resultsdataset_set=()):
        """
        Tag datasets.

        Args:
            name (str)
            sequencedataset_set (list)
            resultsdataset_set (list)

        Returns:
            tag (dict)
        """
        endpoint_url = self.join_urls(self.base_api_url, 'tag')

        fields = {
            'name': name,
            'sequencedataset_set': sequencedataset_set,
            'resultsdataset_set': resultsdataset_set,
        }
        payload = json.dumps(fields, cls=DjangoJSONEncoder)

        r = self.session.post(
            endpoint_url,
            data=payload)

        if not r.ok:
            raise Exception('failed with error: "{}", reason: "{}"'.format(
                r.reason, r.text))

        return r.json()

