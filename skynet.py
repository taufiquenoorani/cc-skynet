import os
import re
import time
import pytz
import datetime
import json
import threading
import requests
import requests.auth
import logging
import shelve
from zenpy import Zenpy
from zenpy.lib.api_objects import Ticket, Comment, CustomField, User
from dotenv import load_dotenv
from variables import *
from azure.servicebus.control_client import ServiceBusService

load_dotenv()

SKYNET_ZD_CORE_USERNAME = os.getenv('SKYNET_ZD_CORE_USERNAME')
SKYNET_ZD_CORE_PASSWORD = os.getenv('SKYNET_ZD_CORE_PASSWORD')
SKYNET_ZD_CORE_SUBDOMAIN = os.getenv('SKYNET_ZD_CORE_SUBDOMAIN')
SKYNET_AZ_CORE_NAMESPACE = os.getenv('SKYNET_AZ_CORE_NAMESPACE')
SKYNET_AZ_CORE_KEYNAME = os.getenv('SKYNET_AZ_CORE_KEYNAME')
SKYNET_AZ_CORE_KEYVALUE = os.getenv('SKYNET_AZ_CORE_KEYVALUE')
SKYNET_AZ_CORE_ENDPOINT = os.getenv('SKYNET_AZ_CORE_ENDPOINT')
API_KEY = os.getenv('API_KEY')
IM_CHANNEL_ID = os.getenv('IM_CHANNEL_ID')

# Zendesk Creds
creds = {
    'email': SKYNET_ZD_CORE_USERNAME,
    'password': SKYNET_ZD_CORE_PASSWORD,
    'subdomain': SKYNET_ZD_CORE_SUBDOMAIN
}

# Creating Service Bus
bus_service = ServiceBusService(
    service_namespace=SKYNET_AZ_CORE_NAMESPACE,
    shared_access_key_name=SKYNET_AZ_CORE_KEYNAME,
    shared_access_key_value=SKYNET_AZ_CORE_KEYVALUE)

print("Created bus_service object")


def service_bus_listener(callback):
    """thread worker function"""
    print('Started listening to service bus messages')
    while True:
        msg = bus_service.receive_queue_message('skynet', peek_lock=False, timeout=60)
        if msg.body is not None:
            process_message(msg)
        else:
            print("No message to process. Backing off for 5 seconds")
            time.sleep(5)


def process_message(msg):
    try:
        global conv

        message = json.loads(msg.body.decode())

        conversation = message.get("conversation")
        token = message.get('from').get('token')
        # Get channel ID
        channel = message.get('channelData').get('teamsChannelId')

        print(message)
        logging.basicConfig(level=logging.INFO, filename='skynet.log', filemode='w', format='%(asctime)s :: %(message)s')
        logging.info(message)

        # Add conversation ID to list
        conv = conversation['id']

        # Add token to User Token list
        if token:
            user_token.append(token)

        # Ask user to select the schedule
        if str(message.get('id')).startswith('f') and message.get('value').get('schedule'):
            select_index = message.get("value")['schedule']
            user = schedule_user[int(select_index)]
            send_oncall(user)

        # Get response back from user after schedule selection
        elif str(message.get('id')).startswith('f') and message.get('value').get('page'):
            select_index = message.get("value")['page']
            user = schedule_user[int(select_index)]
            list_user(user)

        # Get response back from user after user selection
        elif str(message.get('id')).startswith('f') and message.get('value').get('user'):
            select_index = message.get("value")['user']
            # Page user by id
            page_user(user_info.get(int(select_index))[0])
            # Send confirmation back to user by name
            send_page(user_info.get(int(select_index))[1])

        # Get user data after running skynet fire
        elif str(message.get('id')).startswith('f') and message.get('value').get('fire_dc'):
            # Teams URL
            incident_mgmt = 'https://graph.microsoft.com/v1.0/teams/db834b83-11f5-44b1-b1ef-e3f0c1c2b0aa/channels/'
            # Team Name
            team = "Incident Management"
            dc = message.get('value').get('fire_dc')
            services = message.get('value').get('services')
            impact = message.get('value').get('impact')
            experience = message.get('value').get('experience')
            page = message.get('value').get('ui_page')

            # Get name from Activity Object
            zd_name = message.get("from").get("name")

            # Setting temporary name from Teams
            tmp_name = zd_name.replace(' ', '').split(',')

            # Rearranging name from Teams to send to Zendesk
            name = tmp_name[1] + ' ' + tmp_name[0]
            email = user_email[-1]

            # Create channel and zd ticket
            create_urgent_ticket(dc, services, impact, experience, name, email)

            # Create urgent channel
            create_urgent_channel(incident_mgmt, dc, services)

            # Send info to the channel
            send_ui_info(team, dc, services, impact, experience)

            if page == 'ic':
                schedule_user.clear()
                list_overrides(UI_PD_SCHEDULES[0])
                for user in schedule_user:
                    skynet_list_user(user)
            else:
                pass

            # Send confirmation back to User
            channel_url = message.get('channelData').get('channel').get('id')
            incident_confirmation(team, incident_mgmt, channel_url)

        # Get user data after running skynet smoke
        elif str(message.get('id')).startswith('f') and message.get('value').get('smoke_dc'):
            # Teams URL
            incident_mgmt = 'https://graph.microsoft.com/v1.0/teams/db834b83-11f5-44b1-b1ef-e3f0c1c2b0aa/channels/'
            # Team Name
            team = "Incident Management"
            dc = message.get('value').get('smoke_dc')
            services = message.get('value').get('services')
            customer_ticket = message.get('value').get('ticket')
            experience = message.get('value').get('experience')

            # Get name from Activity Object
            zd_name = message.get("from").get("name")

            # Setting temporary name from Teams
            tmp_name = zd_name.replace(' ', '').split(',')

            # Rearranging name from Teams to send to Zendesk
            name = tmp_name[1] + ' ' + tmp_name[0]
            email = user_email[-1]

            # Create channel and zd ticket
            create_high_ticket(dc, services, customer_ticket, experience, name, email)

            # Create High Channel
            create_high_channel(incident_mgmt, dc, services)

            # Send info to the channel
            send_high_info(team, dc, services, customer_ticket, experience)

            # Send confirmation back to User
            channel_url = message.get('channelData').get('channel').get('id')
            incident_confirmation(team, incident_mgmt, channel_url)

        # Get user data after running skynet spark
        elif str(message.get('id')).startswith('f') and message.get('value').get('spark_dc'):
            # Teams URL
            incident_mgmt = 'https://graph.microsoft.com/v1.0/teams/db834b83-11f5-44b1-b1ef-e3f0c1c2b0aa/channels/'
            # Team Name
            team = "Incident Management"
            dc = message.get('value').get('spark_dc')
            services = message.get('value').get('services')
            maintenance_ticket = message.get('value').get('ticket')
            maintenance_engineer = message.get('value').get('engineer')

            # Get name from Activity Object
            zd_name = message.get("from").get("name")

            # Setting temporary name from Teams
            tmp_name = zd_name.replace(' ', '').split(',')

            # Rearranging name from Teams to send to Zendesk
            name = tmp_name[1] + ' ' + tmp_name[0]
            email = user_email[-1]

            # Create channel and zd ticket
            create_maintenance_ticket(dc, services, maintenance_ticket, maintenance_engineer, name, email)

            # Create Maintenance Channel
            create_maintenance_channel(incident_mgmt, dc, services)

            # Send info to the channel
            send_info_maintenance(team, dc, services, maintenance_ticket, maintenance_engineer)

            # Send confirmation back to User
            channel_url = message.get('channelData').get('channel').get('id')
            incident_confirmation(team, incident_mgmt, channel_url)

        # Get user data after running skynet fire
        elif str(message.get('id')).startswith('f') and message.get('value').get('fire_dc_test'):
            # Teams URL
            incident_mgmt = 'https://graph.microsoft.com/v1.0/teams/15fd8009-aec3-4257-b914-fa274588a5b7/channels/'
            # Team Name
            team = "Development Sandbox"
            dc = message.get('value').get('fire_dc_test')
            services = message.get('value').get('services')
            impact = message.get('value').get('impact')
            experience = message.get('value').get('experience')
            page = message.get('value').get('ui_page')

            # Get name from Activity Object
            zd_name = message.get("from").get("name")

            # Setting temporary name from Teams
            tmp_name = zd_name.replace(' ', '').split(',')

            # Rearranging name from Teams to send to Zendesk
            name = tmp_name[1] + ' ' + tmp_name[0]
            email = user_email[-1]

            # Create channel and zd ticket
            create_urgent_ticket(dc, services, impact, experience, name, email)

            # Create urgent channel
            create_urgent_channel(incident_mgmt, dc, services)

            # Send info to the channel
            send_ui_info(team, dc, services, impact, experience)

            if page == 'ic':
                schedule_user.clear()
                list_overrides(UI_PD_SCHEDULES[0])
                for user in schedule_user:
                    skynet_list_user(user)
            else:
                pass

            # Send confirmation back to User
            channel_url = message.get('channelData').get('channel').get('id')
            incident_confirmation(team, incident_mgmt, channel_url)

        # Get user data after running skynet smoke
        elif str(message.get('id')).startswith('f') and message.get('value').get('smoke_dc_test'):
            # Teams URL
            incident_mgmt = 'https://graph.microsoft.com/v1.0/teams/15fd8009-aec3-4257-b914-fa274588a5b7/channels/'
            # Team Name
            team = "Development Sandbox"
            dc = message.get('value').get('smoke_dc_test')
            services = message.get('value').get('services')
            customer_ticket = message.get('value').get('ticket')
            experience = message.get('value').get('experience')

            # Get name from Activity Object
            zd_name = message.get("from").get("name")

            # Setting temporary name from Teams
            tmp_name = zd_name.replace(' ', '').split(',')

            # Rearranging name from Teams to send to Zendesk
            name = tmp_name[1] + ' ' + tmp_name[0]
            email = user_email[-1]

            # Create channel and zd ticket
            create_high_ticket(dc, services, customer_ticket, experience, name, email)

            # Create High Channel
            create_high_channel(incident_mgmt, dc, services)

            # Send info to the channel
            send_high_info(team, dc, services, customer_ticket, experience)

            # Send confirmation back to User
            channel_url = message.get('channelData').get('channel').get('id')
            incident_confirmation(team, incident_mgmt, channel_url)

        # Get user data after running skynet spark
        elif str(message.get('id')).startswith('f') and message.get('value').get('spark_dc_test'):
            # Teams URL
            incident_mgmt = 'https://graph.microsoft.com/v1.0/teams/15fd8009-aec3-4257-b914-fa274588a5b7/channels/'
            # Team Name
            team = "Development Sandbox"
            dc = message.get('value').get('spark_dc_test')
            services = message.get('value').get('services')
            maintenance_ticket = message.get('value').get('ticket')
            maintenance_engineer = message.get('value').get('engineer')

            # Get name from Activity Object
            zd_name = message.get("from").get("name")

            # Setting temporary name from Teams
            tmp_name = zd_name.replace(' ', '').split(',')

            # Rearranging name from Teams to send to Zendesk
            name = tmp_name[1] + ' ' + tmp_name[0]
            email = user_email[-1]

            # Create channel and zd ticket
            create_maintenance_ticket(dc, services, maintenance_ticket, maintenance_engineer, name, email)

            # Create Maintenance Channel
            create_maintenance_channel(incident_mgmt, dc, services)

            # Send info to the channel
            send_info_maintenance(team, dc, services, maintenance_ticket, maintenance_engineer)

            # Send confirmation back to User
            channel_url = message.get('channelData').get('channel').get('id')
            incident_confirmation(team, incident_mgmt, channel_url)

        # Display result after launch
        elif str(message.get('id')).startswith('f') and message.get('value').get('incident') == 'fire':
            # Clear schedule
            schedule_user.clear()

            # Skynet Fire
            skynet_fire()

        elif str(message.get('id')).startswith('f') and message.get('value').get('incident') == 'smoke':
            # Clear schedule
            schedule_user.clear()

            # Skynet Smoke
            skynet_smoke()

        elif str(message.get('id')).startswith('f') and message.get('value').get('incident') == 'spark':
            # Clear schedule
            schedule_user.clear()

            # Skynet Spark
            skynet_spark()

        # Display result after test launch
        elif str(message.get('id')).startswith('f') and message.get('value').get('incident') == 'test_fire':
            # Clear schedule
            schedule_user.clear()

            # Skynet Fire
            test_skynet_fire()

        elif str(message.get('id')).startswith('f') and message.get('value').get('incident') == 'test_smoke':
            # Clear schedule
            schedule_user.clear()

            # Skynet Smoke
            test_skynet_smoke()

        elif str(message.get('id')).startswith('f') and message.get('value').get('incident') == 'test_spark':
            # Clear schedule
            schedule_user.clear()

            # Skynet Spark
            test_skynet_spark()

        else:
            # Strip message to remove whitespace and newline
            _msg = message.get('text').strip()
            strip_msg = ""

            if _msg.startswith("<at>Skynet</at> "):
                strip_msg = _msg.replace("<at>Skynet</at> ", "")
            elif _msg.startswith("<at>Skynet</at>"):
                strip_msg = _msg.replace("<at>Skynet</at>", "")

            # Check if message has "pd page" to pageout users
            if strip_msg.startswith('pd page user'):
                # Clear schedule
                schedule_user.clear()
                # Append to page_channel
                page_channel.append(channel)
                # Get the name of the user
                get_user = strip_msg.split(' ')[3]
                list_user(get_user.title())

            # Check if message has "pd who" to identify on-call
            elif strip_msg.startswith('pd who is'):
                # Clear schedule
                schedule_user.clear()
                get_schedule = strip_msg.split(' ')[3]
                list_schedules(get_schedule.title())

            # Check if message has "pd page team" to page team
            elif strip_msg.startswith('pd page team'):
                # Clear schedule
                schedule_user.clear()
                # Append to page_channel
                page_channel.append(channel)
                # Get the name of the team
                get_schedule = strip_msg.split(' ')[3]
                page_schedules(get_schedule.title())

            # Skynet Fire
            elif strip_msg.startswith('fire'):
                run_launch()

            # Skynet Smoke
            elif strip_msg.startswith('smoke'):
                run_launch()

            # Skynet Spark
            elif strip_msg.startswith('spark'):
                run_launch()

            # Skynet Test Launch
            elif strip_msg.endswith('test'):
                user_email.append(message.get('from').get('tokenIssuedBy').lower())
                test_skynet_launch()

            # Skynet Launch
            elif strip_msg.startswith('launch'):
                user_email.append(message.get('from').get('tokenIssuedBy').lower())
                skynet_launch()

            # skynet resolve
            elif strip_msg.startswith('resolve') or strip_msg.startswith('extinguish'):
                incident_channel = message.get('channelData').get('channel').get('id')
                channel = message.get('channelData').get('channel').get('name')
                teams_id = message.get('channelData').get('team').get('aadObjectId')
                resolve_incident(channel, incident_channel, teams_id)
                resolve_ticket(channel)

            # skynet lower
            elif strip_msg.startswith('lower') or strip_msg.startswith('low'):
                incident_channel = message.get('channelData').get('channel').get('id')
                channel = message.get('channelData').get('channel').get('name')
                teams_id = message.get('channelData').get('team').get('aadObjectId')
                low_ticket(channel)

            # skynet I am IC
            elif strip_msg.lower() == 'i am ic':
                ic_name = message.get('from').get('name')
                channel = message.get('channelData').get('channel').get('name')
                # Setting temporary name from Teams
                tmp_name = ic_name.replace(' ', '').split(',')
                # Rearranging name from Teams to send to Zendesk
                name = tmp_name[1] + ' ' + tmp_name[0]
                email = message.get('from').get('tokenIssuedBy').lower()
                # Send information to channel
                i_am_ic(channel, name, email, 'Incident Commander')

            # Help section
            elif strip_msg.startswith('help'):
                skynet_help()

            # Else pass
            else:
                pass

    except Exception as e:
        print(e)


def run_launch():
    msg = {
        "type": "message",
        "textFormat": "xml",
        "text": "Please run <b>@Skynet launch</b> instead.",
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }

    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


def list_user(user):
    QUERY = user
    url = 'https://api.pagerduty.com/users'
    headers = {
        'Accept': 'application/vnd.pagerduty+json;version=2',
        'Authorization': 'Token token={token}'.format(token=API_KEY)
    }
    payload = {
        'query': QUERY
    }
    r = requests.get(url, headers=headers, params=payload)
    result = r.json()
    user_id = result.get('users')[0].get('id')
    users = result.get('users')

    # Send user schedule
    if len(users) > 1:
        select_user(users)
    else:
        page_user(user_id)
        send_page(user)
        # Clear schedule
        schedule_user.clear()


def skynet_list_user(user):
    QUERY = user
    url = 'https://api.pagerduty.com/users'
    headers = {
        'Accept': 'application/vnd.pagerduty+json;version=2',
        'Authorization': 'Token token={token}'.format(token=API_KEY)
    }
    payload = {
        'query': QUERY
    }
    r = requests.get(url, headers=headers, params=payload)
    result = r.json()
    user_id = result.get('users')[0].get('id')

    # Send user schedule
    page_oncall(user_id)
    send_page(user)


# page team schedule or page user will call this function
def page_user(user_id):
    SERVICE_ID = 'PGZ26VN'
    FROM = 'skynet@ctl.io'
    url = 'https://api.pagerduty.com/incidents'
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/vnd.pagerduty+json;version=2',
        'Authorization': 'Token token={token}'.format(token=API_KEY),
        'From': FROM
    }

    payload = {
        "incident": {
            "type": "incident",
            "title": "Your assistance has been requested in Microsoft Teams - Sent by Skynet",
            "service": {
                "id": SERVICE_ID,
                "type": "service_reference"
            },
            "assignments": [{
                "assignee": {
                    "id": user_id,
                    "type": "user_reference"
                }
            }],
            "incident_key": "baf7cf21b1da41b4b0221008339ff3571",
            "body": {
                "type": "incident_body",
                "details": "Please join Microsoft Teams Channel https://teams.microsoft.com/l/channel/{}/channel".format(
                    page_channel[-1])
            }
        }
    }

    requests.post(url, headers=headers, data=json.dumps(payload))


# skynet fire will call this function
def page_oncall(user_id):
    SERVICE_ID = 'PGZ26VN'
    FROM = 'skynet@ctl.io'
    url = 'https://api.pagerduty.com/incidents'
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/vnd.pagerduty+json;version=2',
        'Authorization': 'Token token={token}'.format(token=API_KEY),
        'From': FROM
    }

    payload = {
        "incident": {
            "type": "incident",
            "title": "Your assistance has been requested in Microsoft Teams - Sent by Skynet",
            "service": {
                "id": SERVICE_ID,
                "type": "service_reference"
            },
            "assignments": [{
                "assignee": {
                    "id": user_id,
                    "type": "user_reference"
                }
            }],
            "incident_key": "",
            "body": {
                "type": "incident_body",
                "details": "Please join Microsoft Teams Channel {}".format(active_channel[-1])
            }
        }
    }

    requests.post(url, headers=headers, data=json.dumps(payload))


def list_schedules(schedule):
    url = 'https://api.pagerduty.com/schedules'
    headers = {
        'Accept': 'application/vnd.pagerduty+json;version=2',
        'Authorization': 'Token token={token}'.format(token=API_KEY)
    }
    payload = {
        'query': schedule
    }
    r = requests.get(url, headers=headers, params=payload)
    result = r.json()
    sch = result['schedules']

    # Iterate through the list of schedules and append to schedule_title
    for schedules in sch:
        schedule_title.append(schedules['name'])

        # Append schedule using ID
        schedule_id.append(schedules['id'])

    count = 0
    while count < len(schedule_id):
        list_overrides(schedule_id[count])
        count += 1

    # Ask user to select the schedule they would like to get information for.
    select_schedule()

    # Clear lists
    schedule_id.clear()
    schedule_title.clear()


def page_schedules(schedule):
    url = 'https://api.pagerduty.com/schedules'
    headers = {
        'Accept': 'application/vnd.pagerduty+json;version=2',
        'Authorization': 'Token token={token}'.format(token=API_KEY)
    }
    payload = {
        'query': schedule
    }
    r = requests.get(url, headers=headers, params=payload)
    result = r.json()
    sch = result['schedules']

    # Iterate through the list of schedules and append to schedule_title
    for schedules in sch:
        schedule_title.append(schedules['name'])

        # Append schedule using ID
        schedule_id.append(schedules['id'])

    count = 0
    while count < len(schedule_id):
        list_overrides(schedule_id[count])
        count += 1

    select_page_schedule()

    # Clear lists
    schedule_id.clear()
    schedule_title.clear()


def list_overrides(ids):
    SINCE = datetime.datetime.now(pytz.timezone('US/Pacific'))
    UNTIL = SINCE + datetime.timedelta(minutes=1)
    url = 'https://api.pagerduty.com/schedules/{id}/users'.format(
        id=ids
    )
    headers = {
        'Accept': 'application/vnd.pagerduty+json;version=2',
        'Authorization': 'Token token={token}'.format(token=API_KEY)
    }
    payload = {}
    if SINCE != '':
        payload['since'] = SINCE
    if UNTIL != '':
        payload['until'] = UNTIL
    r = requests.get(url, headers=headers, params=payload)
    result = r.json()

    try:
        # Get the user on-call and append it to schedule_user
        if not result['users']:
            schedule_user.append('No one')
        else:
            on_call = result['users'][0]['name']
            schedule_user.append(on_call)

    except:
        pass


def select_schedule():
    msg = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.0",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "Select the on-call schedule.",
                            "wrap": True
                        },
                        {
                            "type": "Input.ChoiceSet",
                            "placeholder": "",
                            "choices": [
                            ],
                            "id": "schedule",
                            "separator": True,
                            "wrap": True
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Submit"
                        }
                    ]
                }
            }
        ],
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }

    # Go through the list and append the information to payload
    for num, items in enumerate(schedule_title):
        msg['attachments'][0]['content']['body'][1]['choices'].append({"title": items, "value": num})

    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


def select_page_schedule():
    msg = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.0",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "Select team to page.",
                            "wrap": True
                        },
                        {
                            "type": "Input.ChoiceSet",
                            "placeholder": "",
                            "choices": [
                            ],
                            "id": "page",
                            "separator": True,
                            "wrap": True
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Page!"
                        }
                    ]
                }
            }
        ],
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }

    # Go through the list and append the information to payload
    for num, items in enumerate(schedule_title):
        msg['attachments'][0]['content']['body'][1]['choices'].append({"title": items, "value": num})

    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


def select_user(users):
    msg = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.0",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "Select user to page.",
                            "wrap": True
                        },
                        {
                            "type": "Input.ChoiceSet",
                            "placeholder": "",
                            "choices": [
                            ],
                            "id": "user",
                            "separator": True,
                            "wrap": True
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Page!"
                        }
                    ]
                }
            }
        ],
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }

    # Clear dictionary
    user_info.clear()
    for num, user in enumerate(users):
        user_info.update({num: [user['id'], user['name']]})
        msg['attachments'][0]['content']['body'][1]['choices'].append({"title": user['name'], "value": num})

    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


# Skynet Fire
def skynet_fire():
    msg = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.0",
                    "body": [
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "items": [
                                        {
                                            "type": "Image",
                                            "style": "Person",
                                            "url": "https://png.pngtree.com/png-vector/20190226/ourlarge/pngtree-fire-logo-icon-design-template-vector-png-image_705401.jpg",
                                            "size": "Small"
                                        }
                                    ],
                                    "width": "auto"
                                },
                                {
                                    "type": "Column",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": "URGENT INCIDENT",
                                            "size": "Large",
                                            "horizontalAlignment": "Left",
                                            "wrap": True,
                                            "weight": "Bolder",
                                            "color": "Attention"
                                        }
                                    ],
                                    "width": "stretch"
                                }
                            ]
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the Primary Impacted Datacenter? ",
                            "wrap": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: VA1, UC1",
                            "id": "fire_dc"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What are the impacted services?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: Control, Network, Compute",
                            "id": "services"
                        },
                        {
                            "type": "TextBlock",
                            "text": "Are there known impacted customers?",
                            "separator": True
                        },
                        {
                            "type": "Input.ChoiceSet",
                            "placeholder": "Placeholder text",
                            "choices": [
                                {
                                    "title": "Yes",
                                    "value": "Yes"
                                },
                                {
                                    "title": "No",
                                    "value": "No"
                                }
                            ],
                            "style": "expanded",
                            "id": "impact"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the customer experience?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: Customers cannot ...",
                            "id": "experience",
                            "isMultiline": True
                        },
                        {
                            "type": "Input.ChoiceSet",
                            "placeholder": "",
                            "choices": [
                                {
                                    "title": "Page IC",
                                    "value": "ic"
                                },
                                {
                                    "title": "Don't Page",
                                    "value": "dont"
                                }
                            ],
                            "style": "expanded",
                            "id": "ui_page",
                            "wrap": True,
                            "value": "both"
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Submit"
                        }
                    ]
                }
            }
        ],
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }

    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


# Skynet Test Fire
def test_skynet_fire():
    msg = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.0",
                    "body": [
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "items": [
                                        {
                                            "type": "Image",
                                            "style": "Person",
                                            "url": "https://png.pngtree.com/png-vector/20190226/ourlarge/pngtree-fire-logo-icon-design-template-vector-png-image_705401.jpg",
                                            "size": "Small"
                                        }
                                    ],
                                    "width": "auto"
                                },
                                {
                                    "type": "Column",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": "URGENT INCIDENT",
                                            "size": "Large",
                                            "horizontalAlignment": "Left",
                                            "wrap": True,
                                            "weight": "Bolder",
                                            "color": "Attention"
                                        }
                                    ],
                                    "width": "stretch"
                                }
                            ]
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the Primary Impacted Datacenter? ",
                            "wrap": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: VA1, UC1",
                            "id": "fire_dc_test"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What are the impacted services?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: Control, Network, Compute",
                            "id": "services"
                        },
                        {
                            "type": "TextBlock",
                            "text": "Are there known impacted customers?",
                            "separator": True
                        },
                        {
                            "type": "Input.ChoiceSet",
                            "placeholder": "Placeholder text",
                            "choices": [
                                {
                                    "title": "Yes",
                                    "value": "Yes"
                                },
                                {
                                    "title": "No",
                                    "value": "No"
                                }
                            ],
                            "style": "expanded",
                            "id": "impact"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the customer experience?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: Customers cannot ...",
                            "id": "experience",
                            "isMultiline": True
                        },
                        {
                            "type": "Input.ChoiceSet",
                            "placeholder": "",
                            "choices": [
                                {
                                    "title": "Page IC",
                                    "value": "ic"
                                },
                                {
                                    "title": "Don't Page",
                                    "value": "dont"
                                }
                            ],
                            "style": "expanded",
                            "id": "ui_page",
                            "wrap": True,
                            "value": "both"
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Submit"
                        }
                    ]
                }
            }
        ],
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }

    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


# Skynet Smoke
def skynet_smoke():
    msg = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.0",
                    "body": [
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "items": [
                                        {
                                            "type": "Image",
                                            "style": "Person",
                                            "url": "https://cdn3.iconfinder.com/data/icons/fire-4/96/fire_smoke-512.png",
                                            "size": "Small"
                                        }
                                    ],
                                    "width": "auto"
                                },
                                {
                                    "type": "Column",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": "HIGH INCIDENT",
                                            "size": "Large",
                                            "horizontalAlignment": "Left",
                                            "wrap": True,
                                            "weight": "Bolder",
                                            "color": "Warning"
                                        }
                                    ],
                                    "width": "stretch"
                                }
                            ]
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the Primary Impacted Datacenter? ",
                            "wrap": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: VA1, UC1",
                            "id": "smoke_dc"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What are the impacted services?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: Control, Network, Compute",
                            "id": "services"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the customer ticket number that prompted this incident?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: 1234567",
                            "id": "ticket"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the customer experience?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: Customers cannot ...",
                            "id": "experience",
                            "isMultiline": True
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Submit"
                        }
                    ]
                }
            }
        ],
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }

    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


# Skynet Test Smoke
def test_skynet_smoke():
    msg = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.0",
                    "body": [
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "items": [
                                        {
                                            "type": "Image",
                                            "style": "Person",
                                            "url": "https://cdn3.iconfinder.com/data/icons/fire-4/96/fire_smoke-512.png",
                                            "size": "Small"
                                        }
                                    ],
                                    "width": "auto"
                                },
                                {
                                    "type": "Column",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": "HIGH INCIDENT",
                                            "size": "Large",
                                            "horizontalAlignment": "Left",
                                            "wrap": True,
                                            "weight": "Bolder",
                                            "color": "Warning"
                                        }
                                    ],
                                    "width": "stretch"
                                }
                            ]
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the Primary Impacted Datacenter? ",
                            "wrap": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: VA1, UC1",
                            "id": "smoke_dc_test"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What are the impacted services?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: Control, Network, Compute",
                            "id": "services"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the customer ticket number that prompted this incident?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: 1234567",
                            "id": "ticket"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the customer experience?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: Customers cannot ...",
                            "id": "experience",
                            "isMultiline": True
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Submit"
                        }
                    ]
                }
            }
        ],
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }

    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


# Skynet Spark
def skynet_spark():
    msg = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.0",
                    "body": [
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "items": [
                                        {
                                            "type": "Image",
                                            "style": "Person",
                                            "url": "https://cdn2.iconfinder.com/data/icons/geometry-forms/154/geometry-star-flash-spark-512.png",
                                            "size": "Small"
                                        }
                                    ],
                                    "width": "auto"
                                },
                                {
                                    "type": "Column",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": "MAINTENANCE",
                                            "size": "Large",
                                            "horizontalAlignment": "Left",
                                            "wrap": True,
                                            "weight": "Bolder",
                                            "color": "Good"
                                        }
                                    ],
                                    "width": "stretch"
                                }
                            ]
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the Primary Impacted Datacenter? ",
                            "wrap": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: VA1, UC1",
                            "id": "spark_dc"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What are the impacted services?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: Control, Network, Compute",
                            "id": "services"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the ticket number for this maintenance?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: 1234567",
                            "id": "ticket"
                        },
                        {
                            "type": "TextBlock",
                            "text": "Who is performing the maintenance?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: Name of an engineer",
                            "id": "engineer"
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Submit"
                        }
                    ]
                }
            }
        ],
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }

    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


# Skynet Test Smoke
def test_skynet_spark():
    msg = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.0",
                    "body": [
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "items": [
                                        {
                                            "type": "Image",
                                            "style": "Person",
                                            "url": "https://cdn2.iconfinder.com/data/icons/geometry-forms/154/geometry-star-flash-spark-512.png",
                                            "size": "Small"
                                        }
                                    ],
                                    "width": "auto"
                                },
                                {
                                    "type": "Column",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": "MAINTENANCE",
                                            "size": "Large",
                                            "horizontalAlignment": "Left",
                                            "wrap": True,
                                            "weight": "Bolder",
                                            "color": "Good"
                                        }
                                    ],
                                    "width": "stretch"
                                }
                            ]
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the Primary Impacted Datacenter? ",
                            "wrap": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: VA1, UC1",
                            "id": "spark_dc_test"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What are the impacted services?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: Control, Network, Compute",
                            "id": "services"
                        },
                        {
                            "type": "TextBlock",
                            "text": "What is the ticket number for this maintenance?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: 1234567",
                            "id": "ticket"
                        },
                        {
                            "type": "TextBlock",
                            "text": "Who is performing the maintenance?",
                            "separator": True
                        },
                        {
                            "type": "Input.Text",
                            "title": "New Input.Toggle",
                            "placeholder": "Ex: Name of an engineer",
                            "id": "engineer"
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Submit"
                        }
                    ]
                }
            }
        ],
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }

    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


# Create UI Ticket
def create_urgent_ticket(dc, services, impact, experience, name, email):
    global ticket_number
    zendesk_client = Zenpy(**creds)

    # Create a new ticket
    ticket_audit = zendesk_client.tickets.create(
        Ticket(subject="URGENT MASTER: {} - {}".format(dc, services),
               requester=User(name='Skynet', email='skynet@ctl.io'),
               comment=Comment(
                   html_body='<h3>Incident Details</h3><pre><code>Data Center: {}<br>Impacted Services: {}<br>'
                             'Impacted Customers: {}<br>Customer Experience: {}</code></pre><h3>Submitter Details</h3><pre><code>'
                             'Name: {}<br>Email: {}</code></pre>'.format(dc, services, impact, experience, name,
                                                                         email)),
               priority="urgent", requester_id="1162559009", type="problem",
               submitter_id="1162559009", ticket_form_id="76469", group_id="20048861",
               custom_fields=[
                   CustomField(id=20321291, value='T3N'),
                   CustomField(id=21619801, value='problem'),
               ]))

    ticket_number = ticket_audit.ticket.id

    # Page Team Leads After 2 Hours
    team_page = datetime.datetime.now(pytz.timezone('US/Pacific')) + datetime.timedelta(hours=2)
    convert_time = team_page.strftime('%X')

    # Create database
    with shelve.open('ui', writeback=True) as ui_tickets:
        ticket_number = str(ticket_number)
        ui = {ticket_number: convert_time}
        ui_tickets.update(ui)


# Create UI Channel
def create_urgent_channel(incident_mgmt, dc, services):
    header = {'Authorization': 'Bearer ' + user_token[-1]}

    # Remove whitespace and separate services with -
    services = services.split(' ')
    services = '-'.join(services)

    data = {
        "displayName": "{}-{}-{}".format(ticket_number, dc, services),
        "description": "https://t3n.zendesk.com/agent/tickets/{}".format(ticket_number),
        "isFavoriteByDefault": True
    }

    # Incident Management Teams ID: db834b83-11f5-44b1-b1ef-e3f0c1c2b0aa
    teams_url = incident_mgmt
    response = requests.post(teams_url, json=data, headers=header)
    result = response.json()
    channel_url = result.get('webUrl')

    # Append UI channel to list
    active_channel.append(channel_url)

    # Get channel name
    regex = r"\b\d+(?:-\w+)+(?=\?)"
    matches = re.findall(regex, channel_url)
    channel_name.append(matches[0])

    # Update ZD ticket with channel details
    zendesk_client = Zenpy(**creds)

    ticket = zendesk_client.tickets(id=ticket_number)
    ticket.custom_fields.append(CustomField(id=24373269, value=channel_name[-1]))
    ticket.custom_fields.append(CustomField(id=24333699, value=active_channel[-1]))
    zendesk_client.tickets.update(ticket)


def send_ui_info(team, dc, services, impact, experience):
    msg = {
        "type": "message",
        "textFormat": "xml",
        "text": "<b>Master Incident Ticket#</b> <b><a href=https://t3n.zendesk.com/agent/tickets/{}>{}</a></b><br><b>Impacted Data Center:</b> {}<br>"
                "<b>Impacted Services:</b> {}<br> <b>Impacted Customers:</b> {}<br> <b>Customer Experience:</b> {}<br>".format(ticket_number, ticket_number,
            dc, services, impact, experience),
        "from": {
            "name": "skynet"
        },
        "teamName": team,
        "channelName": channel_name[-1],
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }
    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


# Create High Ticket
def create_high_ticket(dc, services, customer_ticket, experience, name, email):
    global ticket_number
    zendesk_client = Zenpy(**creds)

    # Create a new ticket
    ticket_audit = zendesk_client.tickets.create(
        Ticket(subject="HIGH MASTER: {} - {}".format(dc, services),
               requester=User(name='Skynet', email='skynet@ctl.io'),
               comment=Comment(
                   html_body='<h3>Incident Details</h3><pre><code>Data Center: {}<br>Impacted Services: {}<br>'
                             'Customer Ticket#: {}<br>Customer Experience: {}</code></pre><h3>Submitter Details</h3><pre><code>'
                             'Name: {}<br>Email: {}</code></pre>'.format(dc, services, customer_ticket, experience, name,
                                                                         email)),
               priority="high", requester_id="1162559009", type="incident",
               submitter_id="1162559009", ticket_form_id="65535", group_id="20048861",
               custom_fields=[
                   CustomField(id=20321291, value='T3N'),
                   CustomField(id=21619801, value='problem'),
               ]))

    ticket_number = ticket_audit.ticket.id
    tickets.append(ticket_number)

    # Link High ticket to Master
    try:
        ticket = zendesk_client.tickets(id=customer_ticket)
        ticket.comment = Comment(body="Linking ticket to Master {}".format(ticket_number), public=False)
        ticket.problem_id = ticket_number
        zendesk_client.tickets.update(ticket)
    except:
        msg = {
            "type": "message",
            "textFormat": "xml",
            "text": "<b>Could not link customer ticket. Please check the ticket number and link it manually.</b>",
            "from": {
                "name": "skynet"
            },
            "conversation": {
                "id": conv
            },
            "serviceUrl": "https://smba.trafficmanager.net/amer/"
        }
        requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


# Create High Channel
def create_high_channel(incident_mgmt, dc, services):
    header = {'Authorization': 'Bearer ' + user_token[-1]}

    # Remove whitespace and separate services with -
    services = services.split(' ')
    services = '-'.join(services)

    data = {
        "displayName": "{}-{}-{}".format(ticket_number, dc, services),
        "description": "https://t3n.zendesk.com/agent/tickets/{}".format(ticket_number),
        "isFavoriteByDefault": True
    }

    # Incident Management Teams ID: db834b83-11f5-44b1-b1ef-e3f0c1c2b0aa
    teams_url = incident_mgmt
    response = requests.post(teams_url, json=data, headers=header)
    result = response.json()
    channel_url = result.get('webUrl')

    # Append UI channel to list
    active_channel.append(channel_url)

    # Get channel name
    regex = r"\b\d+(?:-\w+)+(?=\?)"
    matches = re.findall(regex, channel_url)
    channel_name.append(matches[0])

    # Update ZD ticket with channel details
    zendesk_client = Zenpy(**creds)

    ticket = zendesk_client.tickets(id=ticket_number)
    ticket.custom_fields.append(CustomField(id=24373269, value=channel_name[-1]))
    ticket.custom_fields.append(CustomField(id=24333699, value=active_channel[-1]))
    zendesk_client.tickets.update(ticket)


def send_high_info(team, dc, services, customer_ticket, experience):
    msg = {
        "type": "message",
        "textFormat": "xml",
        "text": "<b>Master Incident Ticket#</b> <b><a href=https://t3n.zendesk.com/agent/tickets/{}>{}</a></b><br><b>Impacted Data Center:</b> {}<br>"
                "<b>Impacted Services:</b> {}<br> <b>Customer Ticket#:</b> {}<br> <b>Customer Experience:</b> {}<br>".format(ticket_number, ticket_number,
            dc, services, customer_ticket, experience),
        "from": {
            "name": "skynet"
        },
        "teamName": team,
        "channelName": channel_name[-1],
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }
    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


# Create High Ticket
def create_maintenance_ticket(dc, services, maintenance_ticket, maintenance_engineer, name, email):
    global ticket_number
    zendesk_client = Zenpy(**creds)

    # Create a new ticket
    ticket_audit = zendesk_client.tickets.create(
        Ticket(subject="MAINTENANCE TICKET: {} - {}".format(dc, services),
               requester=User(name='Skynet', email='skynet@ctl.io'),
               comment=Comment(
                   html_body='<h3>Incident Details</h3><pre><code>Data Center: {}<br>Impacted Services: {}<br>'
                             'Maintenace Ticket#: {}<br>Engineer Name: {}</code></pre><h3>Submitter Details</h3><pre><code>'
                             'Name: {}<br>Email: {}</code></pre>'.format(dc, services, maintenance_ticket, maintenance_engineer, name,
                                                                         email)),
               priority="normal", requester_id="1162559009", type="problem",
               submitter_id="1162559009", ticket_form_id="65609", group_id="20048861",
               custom_fields=[
                   CustomField(id=20321291, value='T3N'),
                   CustomField(id=21619801, value='problem'),
               ]))

    ticket_number = ticket_audit.ticket.id
    tickets.append(ticket_number)


# Create Channel
def create_maintenance_channel(incident_mgmt, dc, services):
    header = {'Authorization': 'Bearer ' + user_token[-1]}

    # Remove whitespace and separate services with -
    services = services.split(' ')
    services = '-'.join(services)

    data = {
        "displayName": "{}-{}-{}".format(ticket_number, dc, services),
        "description": "https://t3n.zendesk.com/agent/tickets/{}".format(ticket_number),
        "isFavoriteByDefault": True
    }

    # Incident Management Teams ID: db834b83-11f5-44b1-b1ef-e3f0c1c2b0aa
    teams_url = incident_mgmt
    response = requests.post(teams_url, json=data, headers=header)
    result = response.json()
    channel_url = result.get('webUrl')

    # Append UI channel to list
    active_channel.append(channel_url)

    # Get channel name
    regex = r"\b\d+(?:-\w+)+(?=\?)"
    matches = re.findall(regex, channel_url)
    channel_name.append(matches[0])


def send_info_maintenance(team, dc, services, maintenance_ticket, maintenance_engineer):
    msg = {
        "type": "message",
        "textFormat": "xml",
        "text": "<b>Maintenance Incident Ticket# </b> <b><a href=https://t3n.zendesk.com/agent/tickets/{}>{}</a></b><br><b>Impacted Data Center: </b> {}<br>"
                "<b>Impacted Services: </b> {}<br> <b>Maintenance Ticket#: </b> {}<br> <b>Engineer Name: </b> {}<br>".format(ticket_number, ticket_number,
            dc, services, maintenance_ticket, maintenance_engineer),
        "from": {
            "name": "skynet"
        },
        "teamName": team,
        "channelName": channel_name[-1],
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }
    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


def resolve_ticket(channel):
    try:
        # Get ticket# from the channel
        ticket = int(channel.split('-')[0])

        # Changing priority to normal
        zendesk_client = Zenpy(**creds)
        zd_ticket = zendesk_client.tickets(id=ticket)
        zd_ticket.priority = 'normal'
        zd_ticket.comment = Comment(body="RESOLVED - Lowering priority", public=False)
        zendesk_client.tickets.update(zd_ticket)

        # Get ZD Linked Tickets
        linked_result = requests.get('https://t3n.zendesk.com/api/v2/tickets/{}/incidents.json'.format(ticket),
                                     auth=(SKYNET_ZD_CORE_USERNAME, SKYNET_ZD_CORE_PASSWORD))

        linked_json = linked_result.json()
        linked_tickets = linked_json.get('tickets')

        # Assign linked tickets to IC
        if len(linked_tickets) > 1:
            for linked_ticket in linked_tickets:
                l_ticket_number = int(linked_ticket.get('id'))
                linked_ticket = zendesk_client.tickets(id=l_ticket_number)
                linked_ticket.priority = 'normal'

                zendesk_client.tickets.update(linked_ticket)
        else:
            pass

        # Update the channel
        msg = {
            "type": "message",
            "textFormat": "xml",
            "text": "<b>======== RESOLVED ========</b><br>"
                    "<i>This channel is now unmonitored. Questions regarding this incident can be directed to the IC</i>",
            "from": {
                "name": "skynet"
            },
            "conversation": {
                "id": conv
            },
            "serviceUrl": "https://smba.trafficmanager.net/amer/"
        }
        requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)

    except:
        pass


def low_ticket(channel):
    try:
        # Get ticket# from the channel
        ticket = int(channel.split('-')[0])

        # Changing priority to normal
        zendesk_client = Zenpy(**creds)
        zd_ticket = zendesk_client.tickets(id=ticket)
        zd_ticket.priority = 'normal'
        zd_ticket.comment = Comment(body="Lowering priority", public=False)
        zendesk_client.tickets.update(zd_ticket)

        # Update the channel
        msg = {
            "type": "message",
            "textFormat": "xml",
            "text": "<b>======== LOWERING PRIORITY ========</b><br>"
                    "<i>This channel is now unmonitored. Questions regarding this incident can be directed to the IC</i>",
            "from": {
                "name": "skynet"
            },
            "conversation": {
                "id": conv
            },
            "serviceUrl": "https://smba.trafficmanager.net/amer/"
        }
        requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)

    except:
        pass


# Send the on-call user to Teams
def send_oncall(user):
    msg = {
        "type": "message",
        "textFormat": "xml",
        "text": "<b>{}</b> is on-call".format(user),
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }
    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


# Send confirmation to Teams that user has been paged
def send_page(user):
    msg = {
        "type": "message",
        "textFormat": "xml",
        "text": "PagerDuty user <b>{}</b> has been paged".format(user),
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }
    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


# Send confirmation to Teams that user has been paged
def incident_confirmation(team, incident_mgmt, channel_url):
    try:
        header = {'Authorization': 'Bearer ' + user_token[-1]}

        # Incident Management Teams ID: db834b83-11f5-44b1-b1ef-e3f0c1c2b0aa
        teams_url = incident_mgmt + '{}'.format(channel_url)
        response = requests.get(teams_url, headers=header)
        result = response.json()
        channel = result.get('displayName')

        msg = {
            "type": "message",
            "textFormat": "xml",
            "text": "Master Incident Ticket# <b><a href=https://t3n.zendesk.com/agent/tickets/{}>{}</a></b> and Teams Channel: <b><a href={}>{}</a></b>".format(
                ticket_number, ticket_number, active_channel[-1], channel_name[-1]),
            "from": {
                "name": "skynet"
            },
            "teamName": team,
            "channelName": channel,
            "serviceUrl": "https://smba.trafficmanager.net/amer/"
        }
        requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)

        msg = {
            "type": "message",
            "textFormat": "xml",
            "text": "Master Incident Ticket# <b><a href=https://t3n.zendesk.com/agent/tickets/{}>{}</a></b> and Teams Channel: <b><a href={}>{}</a></b>".format(
                ticket_number, ticket_number, active_channel[-1], channel_name[-1]),
            "from": {
                "name": "skynet"
            },
            "teamName": "Customer Care",
            "channelName": "General",
            "serviceUrl": "https://smba.trafficmanager.net/amer/"
        }
        requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)

    except:
        pass


# Read ticket for status update
def read_ticket():
    try:
        threading.Timer(1.0, read_ticket).start()
        zendesk_client = Zenpy(**creds)

        with shelve.open('ui', flag='r') as ui_tickets:
            # Check status in zendesk ticket
            for channels in channel_name:
                for ticket, tm in ui_tickets.items():
                    if channels.split('-')[0] == ticket:
                        for comment in zendesk_client.tickets.comments(ticket=int(ticket)):
                            if comment.body.startswith('status') or comment.body.startswith('Status'):
                                status_update.update({channels: [comment.body]})

            # Send status to Teams
            for k, v in status_update.items():
                if tmp_status.get(k) != status_update.get(k):
                    msg = {
                        "type": "message",
                        "textFormat": "xml",
                        "text": "{}".format(status_update.get(k)[0]),
                        "from": {
                            "name": "skynet"
                        },
                        "teamName": "Incident Management",
                        "channelName": k,
                        "serviceUrl": "https://smba.trafficmanager.net/amer/"
                    }
                    tmp_status.update({k: v})
                    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)
                else:
                    pass

            # Check time in ticket to page Team Leads after 2 hours
            for ticket, tm in ui_tickets.items():
                zd_response = requests.get('https://t3n.zendesk.com/api/v2/tickets/{}.json'.format(ticket), auth=(SKYNET_ZD_CORE_USERNAME, SKYNET_ZD_CORE_PASSWORD))
                zd_result = zd_response.json()
                ticket_priority = zd_result.get('ticket').get('priority')

                if tm == datetime.datetime.now(pytz.timezone('US/Pacific')).strftime('%X') and ticket_priority == 'urgent':
                    # Clear schedule
                    schedule_user.clear()
                    # Send page to Team Leads
                    list_overrides(TEAM_LEADS[0])
                    for user in schedule_user:
                        skynet_list_user(user)

                    for channel in channel_name:
                        if channel.split('-')[0] == ticket:
                            msg = {
                                "type": "message",
                                "textFormat": "xml",
                                "text": "<b>Team Leads have been paged!</b>",
                                "from": {
                                    "name": "skynet"
                                },
                                "teamName": "Incident Management",
                                "channelName": channel,
                                "serviceUrl": "https://smba.trafficmanager.net/amer/"
                            }
                            requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)
                else:
                    pass

    except:
        pass


# Send on-call IC to channel
def i_am_ic(channel, user, email, role):
    try:
        # Search ZD user
        zd_response = requests.get('https://t3n.zendesk.com/api/v2/users/search.json?query=email:{}'.format(email),
                                   auth=(SKYNET_ZD_CORE_USERNAME, SKYNET_ZD_CORE_PASSWORD))

        zd_result = zd_response.json()
        zd_user_id = zd_result.get('users')[0].get('id')

        if '-' in channel:
            # Get ZD ticket number
            ticket = int(channel.split('-')[0])

            # Update ZD ticket
            zendesk_client = Zenpy(**creds)

            ticket = zendesk_client.tickets(id=ticket)
            ticket.comment = Comment(body="{} is now the {}".format(user, role), public=False)
            ticket.assignee = User(id=zd_user_id, email=email)

            zendesk_client.tickets.update(ticket)

            msg = {
                "type": "message",
                "textFormat": "xml",
                "text": "<b>{}</b> is now the <b>{}</b>. The incident ticket has been reassigned".format(user, role),
                "from": {
                    "name": "skynet"
                },
                "conversation": {
                    "id": conv
                },
                "serviceUrl": "https://smba.trafficmanager.net/amer/"
            }
            requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)
        else:
            not_in_channel(user)

    except:
        pass


# Skynet Help
def skynet_help():
    msg = {
        "type": "message",
        "textFormat": "xml",
        "text": "<b>skynet pd page team <teamName></b> - This command will page a team for you based on the query and what you select.<br> "
                "<b>skynet pd page user <userName></b> - This command will page an individual for you based on the query and what you select.<br>"
                "<b>skynet pd who is <teamName></b> - This command will show you who is on-call currently for the selected team.<br> "
                "<b>skynet launch</b> - This command will begin the process of creating an incident.<br> "
                "<b>skynet I am IC</b> - This command will assign the urgent incident ticket to you.<br>"
                "<b>skynet lower</b> OR <b>low</b> - This command will lower the high incident ticket and assign it to CC Team Leads.<br>"
                "<b>skynet resolve</b> OR <b>extinguish</b> - This command will lower the urgent incident ticket and linked tickets to Normal. It also performs a number of other tasks.<br>"
                "<b>skynet close</b> - This command will create Close Incident tab in the channel with a form required to close and archive the incident.<br>",
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }
    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


def not_in_channel(user):
    msg = {
        "type": "message",
        "textFormat": "xml",
        "text": "<b>{}: </b>You are not in a dedicated Teams channel. Please proceed to the correct channel.".format(user),
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }
    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


def skynet_launch():
    msg = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.0",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Medium",
                            "weight": "Bolder",
                            "text": "SKYNET LAUNCH"
                        },
                        {
                            "type": "TextBlock",
                            "text": "Select the type of incident below.",
                            "wrap": True
                        },
                        {
                            "type": "Input.ChoiceSet",
                            "placeholder": "Placeholder text",
                            "choices": [
                                {
                                    "title": "Fire - Multiple Customers Impacted",
                                    "value": "fire"
                                },
                                {
                                    "title": "Smoke - Single Customer Impacted",
                                    "value": "smoke"
                                },
                                {
                                    "title": "Spark - Maintenance Ticket",
                                    "value": "spark"
                                }
                            ],
                            "id": "incident",
                            "wrap": True
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Submit"
                        }
                    ]
                }
            }
        ],
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }

    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


def test_skynet_launch():
    msg = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.0",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Medium",
                            "weight": "Bolder",
                            "text": "TEST SKYNET LAUNCH"
                        },
                        {
                            "type": "TextBlock",
                            "text": "Select the type of incident below.",
                            "wrap": True
                        },
                        {
                            "type": "Input.ChoiceSet",
                            "placeholder": "Placeholder text",
                            "choices": [
                                {
                                    "title": "Fire - Multiple Customers Impacted",
                                    "value": "test_fire"
                                },
                                {
                                    "title": "Smoke - Single Customer Impacted",
                                    "value": "test_smoke"
                                },
                                {
                                    "title": "Spark - Maintenance Ticket",
                                    "value": "test_spark"
                                }
                            ],
                            "id": "incident",
                            "wrap": True
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": "Submit"
                        }
                    ]
                }
            }
        ],
        "from": {
            "name": "skynet"
        },
        "conversation": {
            "id": conv
        },
        "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }

    requests.post(SKYNET_AZ_CORE_ENDPOINT, json=msg)


def resolve_incident(channel, incident_channel, teams_id):
    header = {'Authorization': 'Bearer ' + user_token[-1]}

    # Rename the channel
    resolved_channel = channel + ' RESOLVED'

    data = {
        "displayName": resolved_channel,
        "isFavoriteByDefault": True
    }

    requests.patch("https://graph.microsoft.com/v1.0/teams/" + teams_id + "/channels/" + incident_channel, json=data, headers=header)


if __name__ == '__main__':
    read_ticket()
    thread = threading.Thread(target=service_bus_listener, args=(process_message,))
    thread.start()


