import json
import requests
import os
import configparser
import json

previously_installed_plugins = {}

admin_base_url = 'http://kong:8001'

def get_admin_plugins():
  return [
    {"target":"routes/adminApi", "payload": {"name": "key-auth", "config": {"key_names": ['X-Kong-Admin-Key']}}},
    {"target":"services/adminApi", "payload": {"name": "file-log", "config": {"path":"/home/kong/log/admin-api.log", "reopen": True}}},
    {"target":"routes/adminApiRegisterInstance", "payload": {"name": "mtls_certs_manager", "config": {
      "ca_private_key_path": "/home/kong/certs/server-ca-key.key",
      "ca_certificate_path": "/home/kong/certs/server-ca-cert.crt"
    }}},
    {"target":"routes/adminApi", "payload": {"name": "client_consumer_validator", "config": {
      "consumer_identifier":"username",
      "rules": {
        "rule_1": {
          "request_path_activation_regex": "(.*)",
          "search_in_header": "X-Certificate-CN-Header",
          "expected_consumer_identifier_regex": "(.*)",
          "methods": ["GET", "HEAD", "PUT", "PATCH", "POST", "DELETE", "OPTIONS", "TRACE", "CONNECT"]
        },
        "rule_2": {
          "request_path_activation_regex": "/services/(.*)/plugins",
          "search_in_json_payload": "config.replace.headers.1",
          "expected_consumer_identifier_regex": "Host:(.*)",
          "methods": ["POST", "PUT", "PATCH"]
        }
      }
    }}},
    {"target": "/", "payload": {"name": "prometheus"}}
  ]

def create_admin_service():
  admin_api_response = requests.get(admin_base_url + '/services/adminApi')
  if admin_api_response.status_code == 404:
    admin_api_payload = {"name": "adminApi", "protocol": "http", "port": 8001, "host": "127.0.0.1"}
    response = requests.post(url=admin_base_url + '/services', data=admin_api_payload, verify=False)
    if response.status_code != 201:
      exit(1)

def create_admin_route():
  create_route('/admin-api', 'adminApi', [])

def create_register_instance_route():
  create_route('/admin-api/instances/register', 'adminApiRegisterInstance', ["POST"])

def create_route(route_path, route_name, methods):
  route_response = requests.get(admin_base_url + '/services/adminApi/routes/' + route_name)
  if route_response.status_code == 404:
    payload = {"name": route_name, "protocols": ["http", "https"], "paths": [route_path], "methods": methods}
    response = requests.post(admin_base_url + '/services/adminApi/routes', data=payload, verify=False)
    if response.status_code != 201:
      exit(1)

def get_api_key():
  config = configparser.ConfigParser()
  api_key_file = os.environ["kong_apikey_file"]
  config.read(api_key_file)
  return config['kong-apikey']['apikey']

def create_consumer():
  api_key = get_api_key()
  key_auth_url = admin_base_url + '/consumers/admin/key-auth'
  admin_consumer_response = requests.get(key_auth_url)
  if admin_consumer_response.status_code == 200 and admin_consumer_response.json()["data"]:
    if admin_consumer_response.json()["data"][0]["key"] != api_key:
      requests.delete(key_auth_url + '/' + admin_consumer_response.json()["data"][0]["id"])
  else:
    requests.post(admin_base_url + '/consumers', data={"username": "admin"}, verify=False)
    requests.post(key_auth_url, data={"key": api_key}, verify=False)

def create_admin():
  create_consumer()
  create_admin_service()
  create_admin_route()
  create_register_instance_route()
  add_plugins()

def get_previous_plugins_for_target(target):
  if target not in previously_installed_plugins:
    previous_plugins = requests.get(get_plugins_path_for_target(target)).json()["data"]
    previously_installed_plugins[target] = list(map(lambda plugin: plugin["name"], previous_plugins))
  return previously_installed_plugins[target]

def target_has_plugin(plugin_name, target):
  return plugin_name in get_previous_plugins_for_target(target)

def add_plugins():
  for plugin_config in get_admin_plugins():
    add_plugin(plugin_config)

def add_plugin(plugin_config):
  target = plugin_config["target"]
  payload = plugin_config["payload"]
  plugin_name = payload["name"]
  if (not target_has_plugin(plugin_name, target)):
    post_plugin_response = requests.post(url=get_plugins_path_for_target(target), data=json.dumps(payload), verify=False, headers={"Content-Type": "application/json"})
    if (post_plugin_response.status_code == 201):
      previously_installed_plugins[target].append(plugin_name)
    else:
      print(post_plugin_response.json())
      exit(1)

def get_plugins_path_for_target(target):
  separator = '' if target.endswith('/') else '/'
  return f"{admin_base_url}{separator}{target}{separator}plugins"

if __name__ == "__main__":
  create_admin()
