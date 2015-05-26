
# Hexoskin Python API Client

A Python client for accessing the Hexoskin API that provides simple, OOP-like access.

This client requires the `requests` python library.

    sudo pip install requests

Initialize a client instance like this:

    api = hexoskin.client.HexoApi('myAPIkey', 'myAPIsecret')


# Authorization

You may pass an authorization object to each request using the `auth` keyword arg:

    trainingroutines = api.trainingroutine.list(auth='someuser@hexoskin.com:someuserpassword')

This might suit your needs, but if you'll be using the same user for all your requests, you can pass it to the api constructor, or set the `auth` attribute on an existing api object:

    api = hexoskin.client.HexoApi('myAPIkey', 'myAPIsecret', auth='someuser@hexoskin.com:someuserpassword')
    api.auth = 'someuser@hexoskin.com:someuserpassword'

The library contains some helper functions for OAuth1 and OAuth2 to help ease the integration process.  For each, there is a method to generate an authorization URL to send the user to, and a method to handle the result of the callback.

For OAuth2 there are three possible options depending on your client grant type.

OAuth2 authentication_code:

    url = api.oauth2_get_request_token_url(callback_uri, grant_type='authorization_code', scope='readonly')
    # Then later after receiving the callback, pass the entire URL into the helper function.
    api.oauth2_get_access_token(callback_uri_with_args)

OAuth2 implicit:

    url = api.oauth2_get_request_token_url(callback_uri, grant_type='implicit', scope='readonly')
    # Then later after receiving the callback, pass the entire URL into the helper function.
    api.oauth2_get_access_token(callback_uri_with_args)

OAuth2 password:

    api.oauth2_get_access_token('username', 'password', scope='readonly')

`callback_uri` should be a valid URL that you control and is in the list of callbacks for your client.  The scope does not have to be 'readonly', but it has to be a scope that is in your client's list of allowed scopes.  At the moment, there are only two scopes, 'readonly' and 'readwrite'.

There is only one flow for OAuth1:

    api.oauth1_get_request_token_url(callback_uri)
    # Then later after receiving the callback, pass the entire URL into the helper function.
    api.oauth1_get_access_token(callback_uri_with_args)

For every OAuth flow, the `api.auth` attribute is populated for you, after a successful OAuth authentication, you can make requests without passing an auth argument into your requests.


# Getting data

Most commonly, you will query the API using the list() or get() methods of a ApiResourceAccessor.  An ApiResourceAccessor is created for each endpoint on an instance of a HexoApi.

Get the current user's info

    user = api.account.list()[0]
    print user

All the users you can see:

    users = api.user.list()
    print users

Passing either keyword arguments or a dictionary to list() sets the GET args of the request.  So any filtering you'd like to apply (that's supported by the API too, of course) can be managed that way.  For instance, of records before a given startTimestamp.

    records = api.record.list(startTimestamp__lt=347477726132)

Or:

    records = api.record.list({'startTimestamp__lt':347477726132})

`records` is a ApiResourceList of record ApiResourceInstances.  You can access it like a list:

    print record[0]

Note that the API resources contained in the record, such as record.user, have also been converted to ApiResourceInstances.

    print record[0].user

You can get the next page by calling load_next() on the list.

    records.load_next()

The next page will be appended to the existing list.  If there is no next page a StopIteration exception is raised.  If you don't want catch the exception, you can check if there is a next page by look at the list's `nexturl`.

    if records.nexturl:
        records.load_next()

You may also user get() to fetch a particular resource by either URI or id.

    user99 = api.user.get(99)

    # or by URI
    user = api.range.get(user99.resource_uri)

But often the library will handle loading objects for you as described in the next section.


## Lazy loading

Often child resources are specified by their URI.  For example, a Range has a User, but when you load a Range, just the URI is returned for the user.  If you wish to know more about the user, say his first_name for example, you would have to load the user with a separate call.  Because this is such a common operation, the library will take care of this for you.

    rng = api.range.list()[0] # rng.user is just a URI right now.
    print rng.user.first_name # the user object is automatically fetched.

Say you have a list of Ranges all from the same user and lazy load an attribute in a loop:

    rngs = api.range.list(user=123) # 20 ranges belonging to user 123
    for r in rngs:
        print r.user.first_name

Clearly it shouldn't be necessary to fetch the user 20 times and happily the library is clever enough to avoid that.  Once the user is loaded once, it's added to an object cache and won't be loaded again until the cache expires (1 hour right now).  If you want to force the library to skip the object cache, pass `force_refresh=True` in your call:

    user = api.user.get(123, force_refresh=True)

To clear out the object cache completely call `clear_object_cache()` on the api object:

    api.clear_object_cache()


The object cache has another benefit, it stores every unique API object only once.  So if you loaded that user again and made a change:

    user = api.user.get(123)
    user.first_name = "Billy Bob"

Every instance of that user is updated, eg. each user object on list of Ranges:

    print rngs[0].user.first_name # prints "Billy Bob"

But you still have to call update to send that change to the server or it will be overwritten the next time you receive that user object from the server:

    user.update()


## The Data Resource

The Data Resource works differently because it doesn't return a list of rows that you can page through, but instead a single response containing all the data that you requested.  Consequently a request to `data` returns an ApiDataList rather than an ApiResourceList.  You can iterate through an ApiDataList to see the ApiDataResult returned for each user (frequently this will be just the current user).  You can query it's length to see how many ApiDataResults were returned

    result = api.data.list(record=99999, datatype__in=(19,33,49))
    len(result)         # -> 1

An ApiDataResult has a `user` attribute that contains the resource_uri of the user and a `data` attribute that contains the returned data points.

    dataresult = result[0]
    dataresult.user     # -> a User ApiResourceInstance '/api/v1/user/99/'
    dataresult.data     # -> an dict of {dataid:[(timestamp, value), ... ], ... } containing one entry for each datatype in the requested data

In the example example we select 3 different datatypes so we need to separate the datatypes, but say we had a query that we *knew* would only return one datatype for one user.  In this case we can simplify the returned data structure by passing `flat=True`:

    result = api.data.list(record=99999, datatype=19, flat=True)

Now `result` is an ApiFlatDataList which is essentially an array of `(timestamp, value)` tuples.  If you are doing some analysis where the timestamps are not relevant, you can leave those off too:

    result = api.data.list(record=99999, datatype=19, flat=True, no_timestamps=True)

Now `result` is simply an array of values.

Be careful to ensure that your result can be flattened when using `flat=True`.  If your query would return mutliple datatypes or data for multiple users, it will be flattened anyhow and you'll have no way to know which data pertains to which datatype or user!


## Creating Resources

You can create items by calling create off any ApiResourceAccessor, a Range for instance:

    new_range = api.range.create({
        'name':'testnew_range',
        'start':353163129199,
        'end':353163139199,
        'user':user
    })

`new_range` is an ApiResourceInstance or, if a resource is not automatically returned from by the API, a string of the URI of the created resource.  You may pass the URI to `api.resource_from_uri()` to load the resource if desired.


## Modifying Resources

You can modify ApiResourceInstances in place and then call update():

    new_range.name = 'newtestyrangey'
    new_range.update()
    print new_range

Or by passing a dictionary to update().  Note that we're using ApiResourceInstances as a values here, regular values work too of course, using an ApiResourceInstance is just a convenience.

    new_range.update({'user': users[0]})
    print new_range


## Deleting Resources

You can delete right from the list!  Modifying our `records` ApiResourceList would send a delete request to the API except it's not allowed.

    try:
        del records[5]
    except hexoskin.errors.MethodNotAllowed, e:
        "Oh no you di'int! %s" % e

Or you can call delete() on a ApiResourceInstance.  That Range we created is probably not worth keeping, let's kill it:

    new_range.delete()


## Exceptions

There are several Exceptions defined by this library.  All but one have to do with HTTP error responses.  Here's the list:

### MethodNotAllowed

This is raised when the library notices you are trying to use a disallowed method.  No request is sent in this case.

    from hexoskin.errors import *
    try:
        api.datatype.list()[4].delete()
    except MethodNotAllowed, e:
        # handle the error somehow...

### HttpError xxx

All HTTP errors inherit from this class so you may use this to catch **all** (even ones without their own class) HTTP errors.  HttpErrors all have a ApiResponse object in `response` which you can examine for more information about the error.

    try:
        # Say you can view, but not change user 5437's annotations
        r = api.annotation.list({'user':5437})[0]
        r.update({'annotation':'I wuz here'})
    catch HttpError, e:
        print e.response


### HttpClientError 4xx
All 400-level HTTP errors inherit from this class so you may use this to catch all 400-level HTTP errors defined below.

 - **HttpBadRequest 400**
 - **HttpUnauthorized 401**
 - **HttpForbidden 403**
 - **HttpNotFound 404**
 - **HttpMethodNotAllowed 405**

### HttpServerError 5xx
All 500-level HTTP errors inherit from this class so you may use this to catch all 500 level HTTP errors defined below.

 - **HttpInternalServerError 500**
 - **HttpNotImplemented 501**


## Cached Resource List

The library derives its resource list by querying the API and stores the result in a local file.  To you can decide where this file is stored by setting the corresponding variable:

    import hexoskin.client
    hexoskin.client.CACHED_API_RESOURCE_LIST = '.api_cache'

To create the filename, the `base_url` has all groups of non-word chars replaced with '.' and is appended to the `CACHED_API_RESOURCE_LIST` value.  In code:

    cache_filename = '%s_%s' % (CACHED_API_RESOURCE_LIST, re.sub(r'\W+', '.', self.base_url))

Setting it to None will disable the caching but that's not recommended, you'll incur a pause each time a HexoApi class is initialized.  To clear the cache, either find and delete the cache file on your system, or call `clear_resource_cache()` on a HexoApi instance.  The next call that requires the resource list will refetch it from the API.

    api.clear_resource_cache()
    api.account.list() # Will refetch the resource list.

If you want to take a look at how the resource is defined (to find available filters for example), you can print it, it's just a normal dict:

    print api.resource_conf

That will likely be a little too large to be useful though.  Each resource is stored separately and links to the configs are available from all the ApiResource[type] classes.

    print api.resource_conf['range']

    # ApiResourceAccessors store a link to the config
    print api.range._conf

    # ApiResourceInstances and ApiResourceLists have a _parent to their ApiResourceAccessor
    print new_range._parent._conf
    print records._conf

You likely won't need that... but it's there!