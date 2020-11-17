from modules.VaultClient import VaultClient
import json
import datetime
from collections import defaultdict
import datetime
from util.util import Util
from dateutil import parser

class AccessManager(object):
    # TODO: add logger in this class
    def __init__(self, vault_client):
        self._vault_client = vault_client
        self._depositor_entity_id = self._vault_client.entity_id
    def grant_access(self, requester_entity_id, dataset_id, expiry_date=None):
        if expiry_date is None:
            expiry_date = (datetime.date.today() + datetime.timedelta(days=14)).strftime("%Y-%m-%d")
        group_name = "_".join((self._depositor_entity_id, dataset_id, "share_group"))
        self._add_member_to_group(group_name, requester_entity_id, expiry_date)
    
    def _add_member_to_group(self, group_name, requester_entity_id, expiry_date):
        read_group_response = self._vault_client.read_group_by_name(group_name)
        member_entity_ids = read_group_response["data"]["member_entity_ids"]
        member_entity_ids.append(requester_entity_id)
        policies = read_group_response["data"]["policies"]
        metadata = read_group_response["data"]["metadata"]
        if metadata is None:
            metadata = {}
        metadata[requester_entity_id] = expiry_date + "," + datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        print (metadata[requester_entity_id])
        self._vault_client.create_or_update_group_by_name(group_name, policies, member_entity_ids, metadata)

    def revoke_access(self, requester_entity_id, dataset_id):
        group_name = "_".join((self._depositor_entity_id, dataset_id, "share_group"))
        self._remove_member_from_group(group_name, requester_entity_id)

    def _remove_member_from_group(self, group_name, requester_entity_id):
        read_group_response = self._vault_client.read_group_by_name(group_name)
        member_entity_ids = read_group_response["data"]["member_entity_ids"]
        member_entity_ids.remove(requester_entity_id)
        policies = read_group_response["data"]["policies"]
        metadata = read_group_response["data"]["metadata"]
        metadata.pop(requester_entity_id, None)
        self._vault_client.create_or_update_group_by_name(group_name, policies, member_entity_ids, metadata)

    def list_members(self):
        members = {}
        members["entity_id"] = self._depositor_entity_id
        members["data"] = []
        depositor_datasets = self._list_datasets()
        if depositor_datasets is None:
            return None
        for each_dataset_id in depositor_datasets:
            group_name = "_".join((self._depositor_entity_id, each_dataset_id, "share_group"))
            each_dataset_members = {}
            each_dataset_members["dataset_id"] = each_dataset_id
            each_dataset_members["members"] = []
            read_group_response = self._vault_client.read_group_by_name(group_name)
            metadata = read_group_response["data"]["metadata"]
            if metadata is None:
                continue
            metadata_defaultdict = defaultdict(lambda: 'None', metadata)
            for each_member_id in self._list_members_per_group(group_name):
                each_member_name = self._vault_client.read_entity_by_id(each_member_id)
                each_member = {"entity_id": each_member_id, "entity_name": each_member_name, "expiry_date": metadata_defaultdict[each_member_id].split(",")[0]}
                each_dataset_members["members"].append(each_member)
            members["data"].append(each_dataset_members)
        return json.dumps(members)
    
    def _list_members_per_group(self, group_name):
        read_group_response = self._vault_client.read_group_by_name(group_name)
        member_entity_ids = read_group_response["data"]["member_entity_ids"]
        return member_entity_ids

    def _list_datasets(self):        
        return self._vault_client.list_secrets(self._depositor_entity_id)

    def expire_shares(self):
        groups = self._vault_client.list_groups()
        for each_group in groups:
            read_group_response = self._vault_client.read_group_by_name(each_group)
            metadata = read_group_response["data"]["metadata"]
            if metadata is None:
                continue
            for key, value in metadata.items():
                expiry_date = datetime.datetime.strptime(value.split(",")[0], "%Y-%m-%d").date()
                if expiry_date <= datetime.date.today():
                    self._remove_member_from_group(each_group, key)

    def find_new_shares(self):
        groups = self._vault_client.list_groups()
        for each_group in groups:
            read_group_response = self._vault_client.read_group_by_name(each_group)
            metadata = read_group_response["data"]["metadata"]
            group_last_update_time = parser.isoparse(read_group_response["data"]["last_update_time"])
            # if (group_last_update_time.replace(tzinfo=None) <= (datetime.datetime.utcnow() - datetime.timedelta(minutes=15))):
            #     continue  

            # no requesters to this dataset
            if metadata is None:
                continue
            depositor_user_id = read_group_response["data"]["name"].split("_")[0]
            dataset_id = read_group_response["data"]["name"].split("_")[1]
            for key, value in metadata.items():
                if len(value.split(",")) > 1:
                    access_updated_time = datetime.datetime.strptime(value.split(",")[1], "%Y-%m-%d %H:%M:%S")
                    print (access_updated_time)
                    nowutc= datetime.datetime.utcnow() 
                    print (nowutc)
                    if access_updated_time <= nowutc and access_updated_time >= (nowutc - datetime.timedelta(minutes=1)):
                        vault_api_url = "http://206-12-90-40.cloud.computecanada.ca/secret/data/{depositor_user_id}/{dataset_id}"\
                                        .format(depositor_user_id=depositor_user_id, dataset_id=dataset_id)
                        app_download_url = "https://github.com/jza201/frdr-secure-data/releases/tag/0.1.0"
                        requester_email = self._vault_client.read_entity_by_id(key)
                        subject = "Vault - Access granted to the request copy of item"
                        # body = (
                        #     "Please refer to the other message first in order to download the dataset itself. "
                        #     "In order to decrypt the data after downloading it, you will need to run our FRDR Vault App"
                        #     "which can be downloaded from [here], and navigate to the Decrypt menu. You will need"
                        #     " to input your FRDR credentials (note: this may be updated to reflect multiple auth sources"
                        #     " later on), and provide the path to the encrypted dataset that you already downloaded,"
                        #     " and a Vault API URL that has been generated for you to access the decryption key"
                        #     "for this dataset, as in this screenshot: [screenshot] \nYour Vault API URL is: {}\n"
                        #     "We strongly recommend only decrypting this data on a trusted computer which is itself "
                        #     "encrypted (e.g. using Windows' BitLocker or Apple's FileVault functionality) and accessed only "
                        #     "by you. You assume full liability for this data upon decryption and the risk of disclosure may be"
                        #     "very significant. If you encounter any problems with this workflow, or you have other feedback "
                        #     "for us, feel free to get in touch at support@frdr-dfdr.ca. Best of luck with the data!"
                        # ).format(vault_api_url)
                        body_html = """\
                            <html>
                                <body>
                                    <p>
                                        Please refer to the other message first in order to download the dataset itself. \
                                        In order to decrypt the data after downloading it, you will need to run our FRDR Vault App \
                                        which can be downloaded from {}, and navigate to the Decrypt menu. You will need \
                                        to input your FRDR credentials (note: this may be updated to reflect multiple auth sources \
                                        later on), and provide the path to the encrypted dataset that you already downloaded, \
                                        and a Vault API URL that has been generated for you to access the decryption key \
                                        for this dataset, as in this screenshot: 
                                    </p>
                                    <img src="../img/decrypt.png">
                                    <p> Your Vault API URL is: {} </p>
                                    <p>
                                        We strongly recommend only decrypting this data on a trusted computer which is itself \
                                        encrypted (e.g. using Windows' BitLocker or Apple's FileVault functionality) and \
                                        accessed only by you. You assume full liability for this data upon decryption and \
                                        the risk of disclosure may be very significant. If you encounter any problems with \
                                        this workflow, or you have other feedback for us, feel free to get in touch at \
                                        support@frdr-dfdr.ca. Best of luck with the data!
                                    </p>
                                    <br/><br/>
                                    FRDR Support
                                    support@frdr-dfdr.ca
                                </body>
                            </html>
                            """.format(app_download_url, vault_api_url)
                        print (requester_email)
                        Util.send_email(requester_email, subject, body_html)
