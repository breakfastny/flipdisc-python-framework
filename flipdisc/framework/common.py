import enum

class REDIS_KEYS(enum.Enum):
    # hashtable used to store all active apps.
    # key is an app name and the value is a json.dumps of all its settings.
    APPS: str = "fd:apps"
    # channel name used to send messages to specific apps.
    # When subscribing, use it as APP_CHANNEL + appname.
    APP_CHANNEL: str = "fd:app:"
    # channel name used to send messages to all apps that use input settings.
    SYS_INPUT_CHANNEL: str = "fd:system:input"
    # channel name used to send messages to all apps that use hdmi settings.
    SYS_HDMI_CHANNEL: str = "fd:system:hdmi"
    # channel name used to send messages to all apps that use output settings.
    SYS_OUTPUT_CHANNEL: str = "fd:system:output"

INPUT_STREAM = "IN_STREAM"
HDMI_INPUT_STREAM = "HDMI_STREAM"

OUTPUT_STREAM = "OUT_STREAM"
