import datetime
import json

import bottle
from bottle import HTTPResponse

from pretenders import settings
from pretenders.log import get_logger
from pretenders.mock_servers.http.handler import HttpHandler
from pretenders.mock_servers.smtp.handler import SmtpHandler
from pretenders.server import app
from pretenders.server.apps import history


LOGGER = get_logger('pretenders.server.apps.pretender')
UID_COUNTER = 0

HANDLERS = {
    'http': HttpHandler(),
    'smtp': SmtpHandler(),
}


def get_pretenders(protocol):
    """
    Get a dict mapping UID to pretender data for the given protocol
    """
    return HANDLERS[protocol].PRETENDERS


def keep_alive(protocol, uid):
    """
    Notification from a mock server that it must be kept  alive.
    """
    get_pretenders(protocol)[uid].keep_alive()


@app.get('/<protocol:re:(http|smtp)>')
def list_pretenders(protocol):
    response = json.dumps(
            [pretender.as_dict()
             for pretender in get_pretenders(protocol).values()])
    #response = json.dumps([{"start": "2013-03-21 18:11:06.716463", "last_call": "2013-03-21 18:11:09.189252", "uid": 1, "timeout": "0:02:00", "name": protocol}, {"start": "2013-03-21 18:11:06.748470", "last_call": "2013-03-21 18:11:06.748470", "uid": 2, "timeout": "0:02:00", "name": "None"}, {"start": "2013-03-21 18:11:09.104860", "last_call": "2013-03-21 18:11:09.104860", "uid": 4, "timeout": "0:02:00", "name": "None"}, {"start": "2013-03-21 18:11:09.107500", "last_call": "2013-03-21 18:11:09.125973", "uid": 5, "timeout": "0:02:00", "name": "None"}, {"start": "2013-03-21 18:11:09.110048", "last_call": "2013-03-21 18:11:09.128202", "uid": 6, "timeout": "0:02:00", "name": "None"}])
    return response


@app.get('/<protocol:re:(http|smtp)>/<uid:int>')
def pretender_get(protocol, uid):
    """
    Get details for a given pretender, defined by protocol and UID
    """
    bottle.response.content_type = 'application/json'
    try:
        return get_pretenders(protocol)[uid].as_json()
    except KeyError:
        raise HTTPResponse("No matching {0} mock".format(protocol),
                           status=404)


@app.post('/<protocol:re:(http|smtp)>')
def create_pretender(protocol):
    """
    Client is requesting a mock instance for the given protocol.

    Generate a new UID for the pretender.
    Return the location of the pretender instance.

    Instance creation is protocol-dependent. For HTTP the same boss
    server will act as pretender in a given sub-URL. For other
    protocols, new processes may be spawn and listen on different
    ports.
    """
    global UID_COUNTER
    UID_COUNTER += 1
    uid = UID_COUNTER

    post_body = bottle.request.body.read().decode('ascii')
    body_data = json.loads(post_body)
    timeout = body_data.get('pretender_timeout', settings.TIMEOUT_PRETENDER)
    name = body_data.get('name')
    LOGGER.info("Creating {0} pretender access point at {1} (name: {2}) {3}"
                .format(protocol, uid, name, timeout))

    return HANDLERS[protocol].get_or_create_pretender(uid, timeout, name)


@app.delete('/<protocol:re:(http|smtp)>/<uid:int>')
def delete_mock(protocol, uid):
    "Delete http mock servers"
    LOGGER.info("Performing delete on {0} pretender {1}"
                .format(protocol, uid))
    HANDLERS[protocol].delete_pretender(uid)
    history.clear_history(uid)


@app.delete('/<protocol:re:(http|smtp)>')
def pretender_delete(protocol):
    """
    Delete pretenders with filters

    Currently only supports ``stale`` argument which deletes all those that
    have not had a request made in a period longer than the time out set on
    creation.
    """
    LOGGER.debug("Got DELETE request: {0}".format(bottle.request.GET))
    if bottle.request.GET.get('stale'):
        LOGGER.debug("Got request to delete stale pretenders")
        # Delete all stale requests
        now = datetime.datetime.now()
        for uid, server in get_pretenders(protocol).copy().items():
            LOGGER.debug("Pretender: {0}".format(server))
            if server.last_call + server.timeout < now:
                LOGGER.info("Deleting pretender with UID: {0}".format(uid))
                delete_mock(protocol, uid)
