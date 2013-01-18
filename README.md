

A Python client for accessing the Hexoskin API.

It provides simple, OOP-like access:

        api = hexoskin.client.HexoApi(user_auth='someuser@hexoskin.com:someuserpassword')

Get the current user's info

    user = api.account.list()[0]
    print user

All the users you can see:

    users = api.user.list()
    print users[0]

Get a list of resources, datatype for instance.
    datatypes = api.datatype.list()

`datatypes` is a ApiResourceList of ApiResourceInstances.  You can access it like a list:

    print datatypes[0]

You can get the next page.

    datatypes.next()

Now datatypes is 40 items long.

You can delete right from the list!  This would send a delete request to the API except it's not allowed.

    try:
        del datatypes[5]
    except hexoskin.errors.MethodNotAllowed, e:
        "Oh no you di'nt! %s" % e

You can create items, a Range for instance:

    new_range = api.range.create({'name':'testnew_range', 'start':10000, 'end':10999, 'user':user.resource_uri})

`new_range` is an ApiResourceInstance.  You can modify it in place:

    new_range.name = 'newtestyrangey'

And update the server:

    new_range.update()
    print new_range

Or by passing a dictionary to update(), note how I can use an ApiResourceInstance as a value here.  That works with the assignment method above too:

    new_range.update({'user': users[0]})
    print new_range

# And of course, delete it:

    new_range.delete()


The library derives it's members by querying the API and stores the result locally.