## aws-snapshot tool for Amazon EC2 instances

### What is aws-snapshot
aws-snapshot it is a free and simple cmd tool for create and manage backup snapshots for multiple EC2 EBS volumes. 
This script create new 'tagged' snapshot, and then search and delete all other tagged snapshots that was created more than 15 days ago.
After execution - script can send slack, email or remote-api notification with current snapshots status.

Script can be run with 3 different action:

* default - perform create snapshot and delete expired snapshots.
* status - only print status and do not do anything.
* delete - only delete expired snapshots without creating new.
* create - only create new snapshots without deleting expired.

Script can work with **IAM-Role** or AWS credentials that was added in configuration file or in **ENV**. 
Script try get current AWS region and instance-name tag from ec2-instance-metadata.

### aws-snapshots basic usage
By default script runs with **default** action, with **IAM-Role** permissions, without any external notification and try search and load **snapshot.json** config file.

#### Command line arguments
Script can be run with several command line arguments: 

* -h --help - print help
* --config - specify configuration file for script
* --aws_key_id - specify AWS Key ID
* --aws_secret_key - specify AWS Secret Key
* --aws_region - specify AWS Region
* -d --debug - enable debug mode with verbose output
* --action - specify script run action - default\status\create\delete

#### AWS Policy
For have ability to get instance name and manage snapshots, instance should have access to:
* describe instances, snapshots, tags, volumes 
* create snapshots
* delete snapshots

For satisfy all this requirements you can create new AWS Policy and attach it to AWS-Role or to AWS-User: 

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:DescribeVolumeStatus",
                "ec2:DescribeVolumes",
                "ec2:DescribeVolumeAttribute",
                "ec2:DescribeSnapshotAttribute",
                "ec2:DescribeSnapshots",
                "ec2:DescribeTags",
                "ec2:DeleteSnapshot",
                "ec2:DeleteTags",
                "ec2:CreateSnapshot",
                "ec2:CreateTags"
            ],
            "Resource": [
                "*"
            ]
        }
    ]
} 
```

#### Configuration
Script uses **snapshot.json** config file that shoult be located in script directory, but also you can specify path to config file by argument.
Configuration file should be in **JSON** format.

###### AWS Credentials
If your instance created without **IAM-Role** you can set AWS credentials in config file:
```json
{
  "aws_key_id": "xxx",
  "aws_key_secret": "xxx"
}
```

##### Snapshots
For changing count of days after that snapshot should be purged - use *snapshot_expire_days* in configuration file, by default purge all snapshots older than 15 days.
Also can save some expired snapshots, if something going wrong, and new snapshots not created and almost all snapshots are expired, this option called - *snapshot_save_count* by default script save 1 snapshot.  
```json
{
    "snapshot_expire_days": 30,
    "snapshot_save_count": 1
}
```

##### Notifications
On failure or success script can send notifications with information about current snapshots status or with failure logs.
Notification messages creates from templates with macros.

###### Slack
For enable Slack notification you should specify in which status you want get notifications - **failure**, **success** or both, Slack API key, Slack Bot name and channels or users for send notifications.
```json
{
    "slack_notify_on": ["failure", "success"],
    "slack_users": ["#backup_channel", "@myusername"],
    "slack_connection": {
        "api_key": "https://hooks.slack.com/services/xxx",
        "bot_name": "aws-backup-bot"
    }
}
```

###### Email
For enable email notifications you need specify SMTP server, SMTP credentials, TLS

```json
{
    "email_notify_on": ["failure", "success"],
    "email_users": ["myemail@myserver.com", "my-second-email@myserver.com"],
    "smtp_connection": {
        "server": "smtp.myserver.com",
        "port": 587,
        "tls": true,
        "user": "smtp_user",
        "password": "smtp_password",
        "from": "aws-snapshot@myserver.com"
    } 
}
```

###### Message templates

### Build binary
This script uses several python dependency, and for easy deployment better convert this script to standalone binary with [pyInstaller](http://www.pyinstaller.org/):

##### PyInstaller
```bash
pyinstaller --specpath /tmp/ --distpath ./ -F --clean --hidden-import=HTMLParser ./aws-snapshot.py
```

##### RPM
##### DEB

### License
BSD License