import cPickle, json, os, pycurl, re, StringIO, urllib

from hexoskin.errors import *


CACHED_API_RESOURCE_LIST = '.api_stash'

class ApiResourceAccessor(object):

    def __init__(self, conf, api):
        self._conf = conf
        self.api = api


    def list(self, get_args=None, *args, **kwargs):
        self._verify_call('list', 'get')
        if get_args is not None:
            get_args = self.api.convert_instances(get_args)
        response = self.api.get(self._conf['list_endpoint'], get_args, *args, **kwargs)
        return ApiResourceList(response, self)


    def patch(self, new_objects, *args, **kwargs):
        self._verify_call('list', 'patch')
        return self.api.patch(self._conf['list_endpoint'], {'objects':new_objects}, *args, **kwargs)


    def get(self, uri):
        self._verify_call('detail', 'get')
        if type(uri) is int or self._conf['list_endpoint'] not in uri:
            uri = '%s%s/' % (self._conf['list_endpoint'], uri)
        response = self.api.get(uri)
        return ApiResourceInstance(response.result, self)


    def create(self, data, *args, **kwargs):
        self._verify_call('list', 'post')
        data = self.api.convert_instances(data)
        response = self.api.post(self._conf['list_endpoint'], data, *args, **kwargs)
        return ApiResourceInstance(response.result, self)


    def _verify_call(self, access_type, method):
        if method not in self._conf['allowed_%s_http_methods' % access_type]:
            raise MethodNotAllowed('%s method is not allowed on a %s %s' % (method, self._conf['name'], access_type))



class ApiResourceList(object):

    def __init__(self, response, parent):
        self._parent = parent
        self.response = response
        self.nexturl = None
        self.objects = []
        self._append_response(self.response)


    def next(self):
        if self.nexturl:
            response = self._parent.api.get(self.nexturl)
            self._append_response(response)
        else:
            raise IndexError('List is already at the end.')


    def _append_response(self, response):
        self.nexturl = response.result['meta']['next'] if 'next' in response.result['meta'] else None
        self.objects += map(lambda o: ApiResourceInstance(o, self._parent), response.result['objects'])


    def __getitem__(self, key):
        if type(key) is int:
            return self.objects[key]
        else:
            return self.response.result[key]


    def __delitem__(self, key):
        if type(key) is int:
            self.objects[key].delete()
            del self.objects[key]
        else:
            return super(ApiResourceList, self).__delitem__(key)


    def __iter__(self):
        return iter(self.objects)


    def __reversed__(self):
        return reversed(self.objects)


    def __len__(self):
        return len(self.objects)



class ApiResourceInstance(object):

    def __init__(self, obj, parent):
        # Skip __setattr__ for this one. Should we derive from parent._conf.fields instead?
        self.__dict__['fields'] = obj
        self._parent = parent
        for k,v in self.fields.items():
            if k in parent.api.resources and type(v) is dict and 'resource_uri' in v:
                self.fields[k] = ApiResourceInstance(v, parent.api.resources[k])


    def __getattr__(self, name):
        if name in self.fields:
            return self.fields[name]
        raise AttributeError


    def __setattr__(self, name, value):
        if name in self.__dict__['fields']:
            value = self._parent.api.convert_instances({name:value})[name]
        else:
            super(ApiResourceInstance, self).__setattr__(name, value)


    def __str__(self):
        return str(self.fields)


    def update(self, data=None, *args, **kwargs):
        self._parent._verify_call('detail', 'put')
        if data is not None:
            for k,v in data.items():
                setattr(self, k, v)
        response = self._parent.api.put(self.fields['resource_uri'], self.fields, *args, **kwargs)

        if response.result:
            self.fields = response.result.copy()
        else:
            self.fields = dict(self.fields.items() + data.items())


    def delete(self, *args, **kwargs):
        self._parent._verify_call('detail', 'delete')
        response = self._parent.api.delete(self.fields['resource_uri'], *args, **kwargs)
        self.fields = dict((k, None) for k in self.fields.keys())



class ApiHelper(object):

    def __init__(self, base_url=None, user_auth=None):
        super(ApiHelper, self).__init__()
        self.auth_user = None
        self.base_url = None
        self.resource_conf = {}
        self.resources = {}
        self._cache = None

        if base_url is not None:
            self.base_url = base_url
        if user_auth is not None:
            self.auth_user = user_auth
        if CACHED_API_RESOURCE_LIST is not None:
            self._cache = '%s_%s' % (CACHED_API_RESOURCE_LIST, re.sub(r'\W+', '.', self.base_url))



    def __getattr__(self, name):
        if len(self.resources) == 0:
            self.build_resources()
        if name in self.resources:
            return self.resources[name]
        if name in self.resource_conf:
            self.resources[name] = ApiResourceAccessor(self.resource_conf[name], self)
            return self.resources[name]
        else:
            raise AttributeError


    def clear_resource_cache(self):
        if self._cache is not None:
            if os.path.isfile(self._cache):
                os.remove(self._cache)
                self.resources = {}
                self.resource_conf = {}


    def build_resources(self):
        if self._cache is not None:
            try:
                with open(self._cache, 'r') as f:
                    self.resource_conf = cPickle.load(f)
            except IOError:
                self._fetch_resource_list()
                try:
                    with open(self._cache, 'w+') as f:
                        cPickle.dump(self.resource_conf, f)
                except IOError, e:
                    print "Couldn't write to stash file: %s" % e
        else:
            self._fetch_resource_list()


    def _fetch_resource_list(self):
        resource_list = self.get('/api/v1/').result
        for n,r in resource_list.iteritems():
            self.resource_conf[n] = self.get(r['schema']).result
            self.resource_conf[n]['list_endpoint'] = r['list_endpoint']
            self.resource_conf[n]['name'] = n


    def convert_instances(self, value_dict):
        return dict((k,v.resource_uri) if k in self.resources and type(v) is ApiResourceInstance else (k,v) for k,v in value_dict.items())


    def _request(self, path, data=None, curlOpt=None, auth=None, method='Unknown'):
        s = StringIO.StringIO()

        req = pycurl.Curl()
        req.setopt(pycurl.SSL_VERIFYPEER, False)
        req.setopt(pycurl.WRITEFUNCTION, s.write)
        req.setopt(pycurl.HTTPHEADER, ['Accept: application/json', 'Content-type: application/json'])
        req.setopt(pycurl.FOLLOWLOCATION, 1)
        req.setopt(pycurl.MAXREDIRS, 5)
        req.setopt(pycurl.URL, str(self.base_url + path))

        if auth is not None:
            req.setopt(pycurl.USERPWD, auth)
        elif self.auth_user is not None:
            req.setopt(pycurl.USERPWD, self.auth_user)
        
        if data is not None:
            req.setopt(pycurl.POSTFIELDS, json.dumps(data))

        if curlOpt is not None:
            for opt, val in curlOpt:
                #print "  setting curl option %s to %s" % (opt, val)
                req.setopt(opt, val)

        # print 'Sending request: %s/%s/' % (self.base_url, path)
        req.perform()

        response = ApiResponse(req.getinfo(pycurl.HTTP_CODE), req.getinfo(pycurl.EFFECTIVE_URL), self._method_from_curl_options(curlOpt), s.getvalue())
        if response.status_code >= 400:
            self._throw_http_exception(response)

        return response


    def post(self, path, data=None, auth=None):
        opts = [(pycurl.POST, 1)]
        return self._request(path, data, opts, auth)


    def get(self, path, data=None, auth=None):
        if data:
            path  = '%s?%s' % (path, urllib.urlencode(data))
        return self._request(path, auth=auth)


    def put(self, path, data=None, auth=None):
        opts = [(pycurl.CUSTOMREQUEST, 'PUT')]
        return self._request(path, data, opts, auth)


    def patch(self, path, data=None, auth=None):
        opts = [(pycurl.CUSTOMREQUEST, 'PATCH')]
        return self._request(path, data, opts, auth)


    def delete(self, path, auth=None):
        opts = [(pycurl.CUSTOMREQUEST, 'DELETE')]
        return self._request(path, None, opts, auth)


    def _method_from_curl_options(self, options):
        if options is not None:
            o = dict(options)
            if pycurl.POST in o:
                return 'POST'
            if pycurl.CUSTOMREQUEST in o:
                return o[pycurl.CUSTOMREQUEST]
        return 'GET'


    def _throw_http_exception(self, response):
        if response.status_code == 400:
            raise HttpBadRequest(response)
        if response.status_code == 401:
            raise HttpUnauthorized(response)
        if response.status_code == 403:
            raise HttpForbidden(response)
        if response.status_code == 404:
            raise HttpNotFound(response)
        if response.status_code == 405:
            raise HttpMethodNotAllowed(response)
        if response.status_code == 500:
            raise HttpInternalServerError(response)
        if response.status_code == 501:
            raise HttpNotImplemented(response)
        raise HttpError(response)



class HexoApi(ApiHelper):

    def __init__(self, base_url=None, user_auth=None):
        if base_url is None:
            base_url = 'https://api.hexoskin.com'
        return super(HexoApi, self).__init__(base_url, user_auth)



class ApiResponse(object):

    def __init__(self, status_code, url, method, body):
        try:
            self.result = json.loads(body)
        except:
            self.result = body
        self.body = body
        self.status_code = status_code
        self.url = url
        self.method = method

    def success(self):
        200 <= self.status_code < 400

    def __str__(self):
        return '%s %s %s\n%s' % (self.status_code, self.method.ljust(6), self.url, self.result)

