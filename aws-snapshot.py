import boto3
import botocore
from datetime import datetime
from pytz import UTC
from os import getenv, path
from json import load
import requests
import logging
import getopt
import sys
from libs import slacksend


def init_configuration():
    configuration = {
        "aws_region": "",
        "aws_key_id": "",
        "aws_key_secret": "",
        "aws_api_version": "2015-10-01",
        "snapshot_action": "status",
        "snapshot_volumes": ["all"],
        "snapshot_name": "%instance_name%-%volume_id%-%date_short%",
        "snapshot_expire_search": "instance-id-tag",
        "snapshot_expire_days": 15,
        "snapshot_save_count": 3,
        "slack_notify_on": ["failure", "success"],
        "email_notify_on": ["failure", "success"],
        "smtp_connection": {"server": "", "port": 0, "tls": False, "user": "", "password": ""},
        "email_users": [""],
        "slack_connection": {"api_key": "",
                             "bot_name": "aws-backup", "bot_icon_success": ":heart:",
                             "bot_icon_failure": ":broken_heart:"},
        "slack_message_template": {"failure": [], "success": []},
        "slack_users": [""],
        "log_location": "/tmp/aws-snapshot.log",
        "log_level": "INFO",
        "debug": True
    }

    # Try load configuration from local config file
    if path.exists(default_config_file):
        configuration = load_configuration_file(default_config_file)

    # Parsing startup options
    cmd_options = ''
    try:
        cmd_options, cmd_arguments = getopt.getopt(sys.argv[1:], "hd", ["help", "debug", "config=",
                                                                        "action=", "aws_key_id=", "aws_secret_key=",
                                                                        "aws_region="])
    except getopt.GetoptError:
        show_help()

    for cmd_opt, cmd_arg in cmd_options:
        if cmd_opt in ("-h", "--help"):
            show_help()
        elif cmd_opt == "--config":
            configuration = load_configuration_file(configuration_file_path=cmd_arg, exit_on_error=True)
        elif cmd_opt == "--aws_key_id":
            configuration["aws_key_id"] = cmd_arg
        elif cmd_opt == "--aws_secret_key":
            configuration["aws_secret_key"] = cmd_arg
        elif cmd_opt == "--aws_region":
            configuration["aws_region"] = cmd_arg
        elif cmd_opt in ("-d", "--debug"):
            configuration["debug"] = True
        elif cmd_opt in ("--action"):
            configuration["snapshot_action"] = cmd_arg

    # Enable debug for status action
    if configuration["snapshot_action"] == "status":
        configuration["debug"] = True

    # Load configuration from environment
    configuration["aws_region"] = getenv("AWS_DEFAULT_REGION", configuration["aws_region"])
    configuration["aws_key_id"] = getenv("AWS_ACCESS_KEY_ID", configuration["aws_key_id"])
    configuration["aws_key_secret"] = getenv("AWS_SECRET_ACCESS_KEY", configuration["aws_key_secret"])


    # Configure logging
    logging.basicConfig(filename=configuration['log_location'], filemode='w', level=logging.INFO)
    return configuration


def show_help():
    print """Saritasa AWS snapshot tool
Usage:
   -h, --help - for help
   -d, --debug - show debug information
   --config='' - set path for configuration file
   --aws_key_id='' - set AWS_ACCESS_KEY_ID
   --aws_secret_key='' - set AWS_SECRET_ACCESS_KEY
   --aws_region='' - set AWS_DEFAULT_REGION
   --action='' - set script action - 'default\delete\\create\status'
   --snapshot_name='' - set custom snapshot prefix name. Default: %instance_name%-%volume_id%-%date_short%
   --snapshot_expire_search='volume-id|instance-id-tag' - search expired snapshots by special instance-id-tag or by attached volume-id
   --snapshot_expire_days= - set amount of days after that snapshots will be expired
   --snapshot_save_count= - minimum number of snapshots for save"""
    sys.exit(0)


def load_configuration_file(configuration_file_path, exit_on_error=False):
    try:
        with open(configuration_file_path) as data_file:
            try:
                json_configuration = load(data_file)
            except ValueError:
                print ("can`t load config file - {0} - wrong json syntax syntax").format(configuration_file_path)
                sys.exit(1)
            return json_configuration

    except IOError:
        print "can`t load config file - {0}, exiting".format(configuration_file_path)
        if exit_on_error:
            sys.exit(1)


def remove_special_charters(input_string):
    special_characters = "*$?^+,.[]|\/"
    input_string = input_string.translate(None, ''.join(special_characters))

    return input_string


def log_error(error_message=""):
    exceptions_pool.append(error_message)
    logging.error(error_message)
    return


def print_debug_message(debug_message=""):
    logging.info(debug_message)
    if configuration["debug"]:
        print debug_message


def snapshot_generate_name(instance_name="", volume_id=""):
    snapshot_name = configuration["snapshot_name"]

    macros_dict = {"%instance_name%": remove_special_charters(instance_name),
                    "%volume_id%": volume_id,
                    "%date_short%": current_date.strftime("%d-%m-%y")}

    for macro in macros_dict:
        snapshot_name = snapshot_name.replace(macro, macros_dict[macro])

    print_debug_message("Snapshot generated prefix: {0}".format(snapshot_name))

    return snapshot_name


def ec2_get_instance_id():
    try:
        response = requests.get("http://169.254.169.254/latest/meta-data/instance-id", timeout=5)
        return response.text
    except requests.exceptions.ConnectTimeout:
        log_error("Failed to get instance ID: can`t connect to AWS meta-data pool")
        return 'UnknownID'


def ec2_get_instance_name(instance_id):
    instance_name = 'UnknownInstance'

    try:
        instance = ec2.Instance(instance_id)
        for instance_tag in instance.tags:
            if instance_tag["Key"] == "Name" and instance_tag["Value"]:
                instance_name = instance_tag["Value"]
    except:
        log_error("Failed to get instance name: unknown API error")

    return instance_name


def ec2_get_instance_volumes(instance_id):
    volumes_list = []
    instance = ec2.Instance(instance_id)

    if "all" in configuration["snapshot_volumes"]:
        try:
            for volume in instance.volumes.all():
                volumes_list.append(volume.id)
        except:
            log_error("Failed to get instance volumes: unknown API error")
    else:
        volumes_filtered = instance.volumes.filter(VolumeIds=configuration["snapshot_volumes"])
        for volume in volumes_filtered:
            volumes_list.append(volume.id)

    return volumes_list


def ec2_get_instance_snapshots(instance_id):
    snapshots_filtered = None
    instance_volumes_list = ec2_get_instance_volumes(instance_id)
    snapshots_dict = {'snapshots_list_total': [],
                      'snapshots_list_expired': [],
                      'snapshots_list_volumes': {},
                      'snapshots_list_volumes_expired': {}}

    if configuration['snapshot_expire_search'] == 'instance-id-tag':
        snapshots_filtered = ec2.snapshots.filter(Filters=[{"Name": "tag:InstanceId", "Values": [instance_id]}])

    elif configuration['snapshot_expire_search'] == 'volume-id':
        snapshots_filtered = ec2.snapshots.filter(Filters=[{"Name": "volume-id", "Values": instance_volumes_list}])

    for volume in instance_volumes_list:
        snapshots_volume_filtered = ec2.snapshots.filter(Filters=[{"Name": "volume-id", "Values": [volume]}])
        snapshots_dict['snapshots_list_volumes'].update({volume: list(snapshots_volume_filtered)})
        snapshots_dict['snapshots_list_volumes_expired'].update({volume: []})

        for snapshot in snapshots_volume_filtered:
            if (current_date - snapshot.start_time).days + 1 > configuration["snapshot_expire_days"]:
                snapshots_dict['snapshots_list_volumes_expired'][volume].append(snapshot)

        snapshots_dict['snapshots_list_total'] = list(snapshots_filtered)
        snapshots_dict['snapshots_list_expired'] += snapshots_dict['snapshots_list_volumes_expired'][volume]

    return snapshots_dict


def ec2_create_snapshot(volume_id):
    try:
        volume = ec2.Volume(volume_id)
        snapshot_name = snapshot_generate_name(instance_name=current_instance_name, volume_id=volume_id)
        snapshot = volume.create_snapshot(Description=snapshot_name)
        snapshot.create_tags(Tags=[{"Value": snapshot_name, "Key": "Name"},
                                   {"Value": current_instance_id, "Key": "InstanceId"}])

        print_debug_message("making backup for {0}".format(volume_id))
        return snapshot

    except NameError as e:
        print_debug_message("Failed to created instance snapshot: {0}".format(e))
        return False


def slack_send_notification():
    if not configuration["slack_connection"]["api_key"] and configuration["slack_notify_on"]:
        print_debug_message("Error: Slack key does not exists")
        return

    if configuration["snapshot_action"] == "status":
        print_debug_message("Info: Runned with status action. Slack message will be not send")
        return

    slack_action = None
    if exceptions_pool and "failure" in configuration["slack_notify_on"]:
        slack_action = "failure"
    elif "success" in configuration["slack_notify_on"]:
        slack_action = "success"
    else:
        print_debug_message("Info: Slack notifications disabled")
        return

    slack_client = slacksend.SlackSender(configuration["slack_connection"]["api_key"])
    macros_dict = {"%instance_id%": current_instance_id,
                   "%instance_name%": current_instance_name,
                   "%instance_volumes%": ", ".join(map(str, current_instance_snapshots_dict["snapshots_list_volumes"])),
                   "%instance_snapshots_total%": len(current_instance_snapshots_dict["snapshots_list_total"]),
                   "%error_logs%": "\n".join(map(str, exceptions_pool))}

    slack_title = configuration["slack_message_template"][slack_action]["title"]
    slack_message = configuration["slack_message_template"][slack_action]["text"]

    for macro in macros_dict.keys():
        slack_title = slack_title.replace(macro, str(macros_dict[macro]))
        slack_message = slack_message.replace(macro, str(macros_dict[macro]))

    attachment = {"fallback": "",
                  "title": slack_title,
                  "title_link": "https://{0}.console.aws.amazon.com/console/home?region={0}".format(configuration["aws_region"]),
                  "text": slack_message,
                  "color": configuration["slack_message_template"][slack_action]["line_color"],
                  "mrkdwn_in": ["text"]}

    for user in configuration["slack_users"]:
        slack_client.send_message(channel=user,
                                  username=configuration["slack_connection"]["bot_name"],
                                  icon_emoji=configuration["slack_message_template"][slack_action]["icon"],
                                  attachments=[attachment])

        print_debug_message("Sending slack message to: {0}".format(user))


if __name__ == "__main__":
    working_directory = "/tmp/"
    if getattr(sys, "frozen", False):
        working_directory = path.dirname(sys.executable)
    elif __file__:
        working_directory = path.dirname(__file__)

    default_config_file = "{0}/snapshot.json".format(working_directory)
    current_date = datetime.now(UTC)
    exceptions_pool = []
    created_snapshots_pool = []
    configuration = init_configuration()
    # current_instance_id = ec2_get_instance_id()
    current_instance_id = 'i-d69bcbdc'

    # Init AWS session
    try:
        aws_session = boto3.Session(region_name=configuration["aws_region"],
                                    aws_access_key_id=configuration["aws_key_id"],
                                    aws_secret_access_key=configuration["aws_key_secret"])
    except botocore.exceptions.ClientError as e:
        log_error("Failed connect to AWS: {0}".format(e))

    # Connect to AWS ec2 resource point # may be defined in aws session - Resource
    try:
        ec2 = aws_session.resource(service_name="ec2", api_version=configuration["aws_api_version"])
    except:
        log_error("Failed connect to EC2 Resource")

    current_instance_name = ec2_get_instance_name(current_instance_id)
    print_debug_message("InstanceID: {0}\nInstanceName: {1}".format(current_instance_id, current_instance_name))

    # Delete expired snapshots
    current_instance_snapshots_dict = ec2_get_instance_snapshots(current_instance_id)
    snapshots_left = len(current_instance_snapshots_dict['snapshots_list_total'])

    for snapshot_id in current_instance_snapshots_dict['snapshots_list_expired']:
        if snapshots_left <= configuration["snapshot_save_count"]:
            break

        if configuration["snapshot_action"] in ("default", "delete"):
            print_debug_message("deleting snapshot id: {0}".format(snapshot_id.description))
            snapshot_id.delete()
        snapshots_left -= 1

    # Start making snapshots
    if "all" in configuration["snapshot_volumes"]:
        snapshot_volumes = ec2_get_instance_volumes(current_instance_id)
    else:
        snapshot_volumes = configuration["snapshot_volumes"]

    if configuration["snapshot_action"] in ("default", "create"):
        for volume_id in snapshot_volumes:
            ec2_create_snapshot(volume_id)
            created_snapshots_pool.append(volume_id)

    # fix this for speedup
    current_instance_snapshots_dict = ec2_get_instance_snapshots(current_instance_id)

    slack_send_notification()
    print_debug_message("Snapshots total: {0}".format(len(current_instance_snapshots_dict['snapshots_list_total'])))
    print_debug_message("Snapshots expired: {0}".format(len(current_instance_snapshots_dict['snapshots_list_expired'])))
    print_debug_message("Exit")
