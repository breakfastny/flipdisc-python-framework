from attrdict import AttrDict

REDIS_KEYS = AttrDict({
    # hashtable used to store all active apps.
    # key is an app name and the value is a json.dumps of all its settings.
    'APPS': 'fd:apps',

    # channel name used to send messages to specific apps.
    # When subscribing, use it as APP_CHANNEL + appname.
    'APP_CHANNEL': 'fd:app:',

    # channel name used to send messages to all apps that use input settings.
    'SYS_INPUT_CHANNEL': 'fd:system:input'
})

INPUT_STREAM = "IN_STREAM"
OUTPUT_STREAM = "OUT_STREAM"
