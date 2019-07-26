# coding=utf-8
# Licensed Materials - Property of IBM
# Copyright IBM Corp. 2016,2017


"""
REST API bindings for IBM® Streams Cloud Pak for Data & Streaming Analytics build service.

**********************
Streams Build REST API
**********************

The REST Build API provides programmatic support for creating, submitting and managing Streams builds. You can use the REST Build API from any application that can establish an HTTPS connection to the server that is running the build service.  The current support includes only methods for managing toolkits in the build service.

Cloud Pak for Data
==================

:py:meth:`~streamsx.rest_primitives.Instance.of_endpoint` is the entry point to using the Streams Build REST API bindings,
returning an :py:class:`~streamsx.build_service.BuildService`.

**********************************
Streaming Analytics Build REST API
**********************************

You can use the Streaming Analytics build REST API to manage toolkits installed on a build server.  

:py:class:`BuildService` is a wrapper around the Streaming Analytics Build REST API.  This API allows functions such as :py:meth:`get toolkits <streamsx.build_service.BuildService.get_toolkits>` to list the installed toolkits, and :py:meth:`upload toolkit <streamsx.rest_primitives.Toolkit.from_local_toolkit>` to upload a local toolkit to the build service.

.. seealso:: :ref:`sas-main`
"""
from future.builtins import *

import os
import json
import logging
import re
import requests
import tempfile
from pprint import pformat
from zipfile import ZipFile

import streamsx.topology.context

import streamsx._streams._version
__version__ = streamsx._streams._version.__version__

from streamsx import st
from .rest import _AbstractStreamsConnection
from .rest_primitives import (Domain, Instance, Installation, RestResource, Toolkit, _StreamsRestClient, StreamingAnalyticsService, _streams_delegator,
    _exact_resource, _IAMStreamsRestClient, _IAMConstants, _get_username,
    _ICPDExternalAuthHandler, _handle_http_errors)

logger = logging.getLogger('streamsx.build_service')


class BuildService(_AbstractStreamsConnection):
    """Creates a connection to a running distributed IBM Streams build service and exposes methods to manage the toolkits installed on that build service.

    Args:
        username (str): Username of an authorized Streams user. If ``None``, the username is taken from the ``STREAMS_USERNAME`` environment variable.

        password(str): Password for `username` If ``None``, the password is taken from the ``STREAMS_PASSWORD`` environment variable.

        resource_url(str): Root URL for IBM Streams REST API. If ``None``, the URL is taken from the ``STREAMS_REST_URL`` environment variable.

    Example:
        >>> from streamsx.build_service import BuildService
        >>> resource_url = "https://streams.example.com:31843"
        >>> service_name="StreamsInstance"
        >>> build_service = BuildService.of_endpoint(resource_url, service_name, "streamsadmin", "passw0rd")
        >>> toolkits = build_service.get_toolkits()
        >>> print("There are {} toolkits available.".format(len(toolkits)))
        There are 10 toolkits available.

    Attributes:
        session (:py:class:`requests.Session`): Requests session object for making REST calls.
    """
    def __init__(self, username=None, password=None, resource_url=None, auth=None):
        """specify username, password, and resource_url"""
        streamsx._streams._version._mismatch_check(__name__)
        if auth:
            pass
        elif username and password:
            pass
        else:
            raise ValueError("Must supply either an authentication token or a username, password"
                             " to the BuildService constructor.")

        if not resource_url and 'STREAMS_REST_URL' in os.environ:
            resource_url = os.environ['STREAMS_REST_URL']
        
        self._build_url = resource_url
        if auth:
            self.rest_client = _StreamsRestClient(auth)
        else:
            self.rest_client = _StreamsRestClient._of_basic(username, password)
        self.rest_client._sc = self
        self.session = self.rest_client.session

    @property
    def resource_url(self):
        """str: Endpoint URL for IBM Streams REST build API.

        .. versionadded:: 1.13
        """
        if self._build_url:            
            return re.sub('/builds$','/resources', self._build_url)
        return None

    def get_resources(self):
        """Retrieves a list of all known Streams high-level Build REST resources.

        Returns:
            :py:obj:`list` of :py:class:`~.rest_primitives.RestResource`: List of all Streams high-level Build REST resources.

        .. versionadded:: 1.13
        """
        return super().get_resources()

    def get_toolkits(self):
        """Retrieves a list of all installed Streams Toolkits.

        Returns:
            :py:obj:`list` of :py:class:`~.rest_primitives.Toolkit`: List of all Toolkit resources.

        .. versionadded:: 1.13
        """
        return self._get_elements('toolkits', Toolkit)
     
    def get_toolkit(self, id):
        """Retrieves available toolkit matching a specific toolkit ID.

        Args:
            id (str): Toolkit identifier to retrieve.  This is the name and 
                      version of a toolkit.  For sample, `com.ibm.streamsx.rabbitmq-1.1.3`

        Returns:
            :py:class:`~.rest_primitives.Toolkit`: Toolkit matching `id`.

        Raises:
            ValueError: No matching toolkit exists.

        .. versionadded:: 1.13
        """
        return self._get_element_by_id('toolkits', Toolkit, id)

    def upload_toolkit(self, path):
        """
        Upload a toolkit from a directory in the local filesystem to 
        the Streams build service.

        Multiple versions of a toolkit may be uploaded as long as each has
        a unique version.  If a toolkit is uploaded with a name and version
        matching an existing toolkit, it will not replace the existing
        toolkit, and ``None`` will be returned.
       
        Args:
            path(str): The path to the toolkit directory in the local filesystem.
        Returns:
            Toolkit: The created Toolkit, or ``None`` if it was not uploaded.

        .. versionadded:: 1.13
        """
        # Handle path does not exist, is not readable, is not a directory
        if not os.path.isdir(path):
            raise ValueError('"' + path + '" is not a path or is not readable')

        # Create a named temporary file
        with tempfile.NamedTemporaryFile(suffix='.zip') as tmpfile:
            filename = tmpfile.name
        
            basedir = os.path.abspath(os.path.join(path, os.pardir))

            with ZipFile(filename, 'w') as zipfile:
                for root, dirs, files in os.walk(path):
                    # Write the directory entry
                    relpath = os.path.relpath(root, basedir)
                    zipfile.write(root, relpath)
                    for file in files:
                        zipfile.write (os.path.join(root, file), os.path.join(relpath, file))
                zipfile.close()
            
                with open(filename, 'rb') as toolkit_fp:
                    res = self.rest_client.session.post(Toolkit._toolkits_url(self),
                        headers = {'Accept' : 'application/json',
                                   'Content-Type' : 'application/zip'},
                        data=toolkit_fp,
                        verify=self.rest_client.session.verify)
                    _handle_http_errors(res)
                    new_toolkits = list(Toolkit(t, self.rest_client) for t in res.json()['toolkits'])

                    # It may be possible to upload multiple toolkits in one 
                    # post, but we are only uploading a single toolkit, so the
                    # list of new toolkits is expected to contain only one 
                    # element, and we return it.  It is also possible that no 
                    # new toolkit was returned.

                    if len(new_toolkits) >= 1:
                        return new_toolkits[0]    
                    return None

    @staticmethod
    def of_endpoint(endpoint=None, service_name=None, username=None, password=None, verify=None):
        """
        Connect to a Cloud Pak for Data IBM Streams instance from
        outside the cluster.

        Args:
            endpoint(str): Deployment URL for Cloud Pak for Data, e.g. `https://icp4d_server:31843`. Defaults to the environment variable ``ICPD_URL``.
            service_name(str): Streams instance name. Defaults to the environment variable ``STREAMS_INSTANCE_ID``.
            username(str): User name to authenticate as. Defaults to the environment variable ``STREAMS_USERNAME`` or the operating system identifier if not set.
            password(str): Password for authentication. Defaults to the environment variable ``STREAMS_PASSWORD`` or the operating system identifier if not set.
            verify: SSL verification. Set to ``False`` to disable SSL verification. Defaults to SSL verification being enabled.

        Returns:
            BuildService: Connection to Streams build service or ``None`` of insufficient configuration was provided.

        .. versionadded:: 1.13
        """
        if not endpoint:
            endpoint = os.environ.get('ICPD_URL')
            if endpoint:
                if not service_name:
                    service_name = os.environ.get('STREAMS_INSTANCE_ID')
                if not service_name:
                    return None
            else:
                endpoint = os.environ.get('STREAMS_BUILD_URL')
                if not endpoint:
                    return None
        if not endpoint:
            return None
        if not password:
            password = os.environ.get('STREAMS_PASSWORD')
        if not password:
            return None
        username = _get_username(username)

        auth=_ICPDExternalAuthHandler(endpoint, username, password, verify, service_name)

        build_url, _ = BuildService._root_from_endpoint(auth._cfg['connection_info'].get('serviceBuildEndpoint'))

        sc = BuildService(resource_url=build_url, auth=auth)
        if verify is not None:
            sc.rest_client.session.verify = verify
 
        return sc

    @staticmethod
    def _root_from_endpoint(endpoint):
        import urllib.parse as up
        esu = up.urlsplit(endpoint)
        if not esu.path.startswith('/streams/rest/builds'):
            return None, None

        es = endpoint.split('/')
        name = es[len(es)-1]
        root_url = endpoint.split('/streams/rest/builds')[0]
        resource_url = root_url + '/streams/rest/resources'
        return resource_url, name

    def __str__(self):
        return pformat(self.__dict__)

