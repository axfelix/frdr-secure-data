import nacl
import hvac
import logging
from util.util import Util

Util.get_logger("frdr-crypto.key-manager")
class KeyManagementLocal(object):
    def __init__(self):
        self._key = None
        self._logger = logging.getLogger("frdr-crypto.key-mamanger.local")
    
    def generate_key(self):
        self._key = nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)
        self._logger.info("Key is generated using python nacl package.")
    
    def save_key(self, filename):
        with open(filename, 'wb') as f:
            f.write(self._key)
        self._logger.info("Key is saved to local path {}".format(filename))
    
    def read_key(self, filename):
        with open(filename, "rb") as f:
            self._key = f.read()
        self._logger.info("key is read from local path {}".format(filename))

    @property
    def key(self):
        if self._key is None:
            self.generate_key()
        return self._key

class KeyManagementVault(object):
    def __init__(self, vault_client, key_ring_name):
        self._logger = logging.getLogger("frdr-crypto.key-mamanger.vault")
        self._vault_client = vault_client
        self._key_ring_name = key_ring_name #key_ring_name is the dataset_id
        self._key = None
        self._key_ciphertext = None
        self._dataset_access_policy_name = "_".join((self._vault_client.entity_id, self._key_ring_name, "share_policy"))
        self._dataset_access_group_name = "_".join((self._vault_client.entity_id, self._key_ring_name, "share_group"))

    def generate_key(self):
        # enable transit engine should be done by vault admin
        # self._vault_client.enable_transit_engine()
        # added create encryption key permission for frdr-user policy
        self._vault_client.create_transit_engine_key_ring(self._key_ring_name)
        # added generate data key permission for frdr-user policy
        key_plaintext, key_ciphertext = self._vault_client.generate_data_key(self._key_ring_name)
        self._key = Util.base64_to_byte(key_plaintext)
        self._key_ciphertext = key_ciphertext   
        self._logger.info("Key is generated by vault transit secrets engine.")

    def save_key(self, path):
        self._vault_client.save_key_to_vault(path, self._key_ciphertext)
        self._logger.info("Key is saved to vault")

    def read_key(self, path):
        key_ciphertext = self._vault_client.retrive_key_from_vault(path)
         # added decrypt data permission for frdr-user policy
        key_plaintext = self._vault_client.decrypt_data_key(self._key_ring_name, key_ciphertext)
        self._key = Util.base64_to_byte(key_plaintext)
        self._logger.info("key is read from vault")

    def get_vault_entity_id(self):
        return self._vault_client.entity_id

    def create_access_policy_and_group(self):
        if not self._dataset_access_policy_exists():
            self._create_dataset_access_policy()
        if not self._dataset_access_group_exists():
            self._create_dataset_access_group()

    def _dataset_access_policy_exists(self):
        try:
            self._vault_client.read_policy(self._dataset_access_policy_name)
        except hvac.exceptions.InvalidPath:
            self._logger.info("Policy {} does not exist.".format(self._dataset_access_policy_name))
            return False
        return True

    def _create_dataset_access_policy(self):
        policy_string = """
            path "secret/data/{user_entity_id}/{dataset_id}" {{
                capabilities = [ "read", "list", "delete"]
            }}
        """.format(user_entity_id=self._vault_client.entity_id, dataset_id=self._key_ring_name)
        response = self._vault_client.create_policy(self._dataset_access_policy_name, policy_string)
        if response.status_code == 204:
            self._logger.info("Policy {} is created.".format(self._dataset_access_policy_name))
            return True
        else:
            return False

    def _dataset_access_group_exists(self):
        try:
            self._vault_client.read_group_by_name(self._dataset_access_group_name)
        except hvac.exceptions.InvalidPath:
            self._logger.info("Group {} does not exist.".format(self._dataset_access_group_name))
            return False
        return True

    def _create_dataset_access_group(self):
        response = self._vault_client.create_or_update_group_by_name(group_name=self._dataset_access_group_name,
                                                                     policy_name=self._dataset_access_policy_name)
        try:
            group_name = response["data"]["name"]
            self._logger.info("Group {} is created.".format(self._dataset_access_group_name))
            return group_name
        except:
            return False

    @property
    def key(self):
        if self._key is None:
            self.generate_key()
        return self._key