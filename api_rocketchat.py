# rocket_api.py
# import requests
# import json

# with open('config.json') as f:
#     config = json.load(f)

# headers = {
#     'X-Auth-Token': config['auth_token'],
#     'X-User-Id': config['user_id']
# }

# def obtener_mensajes_no_leidos():
#     endpoint = f"{config['rocket_url']}/api/v1/subscriptions.get"
#     response = requests.get(endpoint, headers=headers)
#     data = response.json()

#     mensajes_no_leidos = []
#     if data.get('success'):
#         for canal in data['update']:
#             if canal.get('unread') > 0:
#                 mensajes_no_leidos.append({
#                     'nombre': canal.get('name'),
#                     'mensajes_pendientes': canal.get('unread')
#                 })

#     return mensajes_no_leidos

# if __name__ == "__main__":
#     print(obtener_mensajes_no_leidos())
