from django.conf import settings

'''
    Set default app settings, if not configured in settings.py.
'''
INSTAGRAM_OAUTH_CONFIG_DEFAULT = {
    'client_id': '7bfdcbc4849c4c8d8f56db62fbca8fcb',
    'client_secret': '961f4f739034408ba2c79f635869e1c5',
    'redirect_uri': 'http://www.sherrihill.com'
}

INSTAGRAM_LIKES_OAUTH_CONFIG_DEFAULT = {
    'client_id': '8c70645f198e4249808d7db2b13ae63b',
    'client_secret': '95b20ff1b7654cafbfe9af373874f253',
    'redirect_uri': 'https://sherrihill.com'
}

QUERY_OBJECTS_PER_PAGE = 33 # Please don't change this, straight from the Instagram API results.
MAX_INSTAGRAM_API_CALLS_DEFAULT = 500
INSTAGRAM_TASK_BROKER_DEFAULT = 'redis://localhost:6379/0'
GET_LIKES_LATEST_COUNT_DEFAULT = 200



'''
    Get attributes set in settings.py. If they don't exist, use defaults.
'''
INSTAGRAM_OAUTH_CONFIG = getattr(settings, 'INSTAGRAM_OAUTH_CONFIG', INSTAGRAM_OAUTH_CONFIG_DEFAULT)
INSTAGRAM_LIKES_OAUTH_CONFIG = getattr(settings, 'INSTAGRAM_LIKES_OAUTH_CONFIG', INSTAGRAM_LIKES_OAUTH_CONFIG_DEFAULT)
MAX_INSTAGRAM_API_CALLS = getattr(settings, 'MAX_INSTAGRAM_API_CALLS', MAX_INSTAGRAM_API_CALLS_DEFAULT)
INSTAGRAM_TASK_BROKER = getattr(settings, 'INSTAGRAM_TASK_BROKER', INSTAGRAM_TASK_BROKER_DEFAULT)
GET_LIKES_LATEST_COUNT = getattr(settings, 'GET_LIKES_LATEST_COUNT', GET_LIKES_LATEST_COUNT_DEFAULT)
