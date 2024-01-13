from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import pandas as pd
import re
import json

adminkey = 'WuvBpW11RoH8sOOxh195DVPoNLY7vhTTWD1KCLtH7oAzSeCvk2DP'
endpoint = 'https://smartagentknowledgebase.search.windows.net'
credential = AzureKeyCredential(adminkey)
index_name = 'iplauction2023'


df = pd.read_csv('iplauction2023.csv')

searchclient = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)

data = []
id = 0
# for _, row in df.iterrows():
#     data.append({
#         "@search.action" : "upload",
#         "id" : str(id),
#         "name" : row["name"],
#         "role" : row["role"],
#         "nationality" : row["nationality"],
#         "baseprice" : row["baseprice"],
#         "finalprice" : row["finalprice"],
#         "franchise" : row["franchise"],
#         "status" : row["status"]
#     })

#     id+=1

for _, row in df.iterrows():
    base_price = row["baseprice"] if not pd.isna(row["baseprice"]) else 0
    final_price = row["finalprice"] if not pd.isna(row["finalprice"]) else 0

    data.append({
        "@search.action": "upload",
        "id": str(id),
        "name": row["name"],
        "role": row["role"],
        "nationality": row["nationality"],
        "baseprice": str(base_price),
        "finalprice": str(final_price),
        "franchise": str(row["franchise"]),
        "status": row["status"]
    })

    id += 1

# print("Generated JSON:", json.dumps(data, indent=2))
# print(len(data))

# print(type(data[37]["status"]))

result = searchclient.upload_documents(data)
print("Upload result : {}".format(result))