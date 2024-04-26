import openai
import os
from pathlib import Path  
import json
import time
from azure.search.documents.models import Vector  
import uuid

#
from tenacity import retry, wait_random_exponential, stop_after_attempt, RetryError  

#
import traceback

from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential  
from azure.search.documents import SearchClient  
# from openai.embeddings_utils import get_embedding, cosine_similarity
import inspect
env_path = Path('.') / 'secrets.env'
load_dotenv(dotenv_path=env_path)

# openai.api_key =  os.environ.get("AZURE_OPENAI_API_KEY")
# openai.api_base =  os.environ.get("AZURE_OPENAI_ENDPOINT")
# openai.api_type = "azure"
# emb_engine = os.getenv("AZURE_OPENAI_EMB_DEPLOYMENT")
# emb_engine = emb_engine.strip('"')

# #azcs implementation
# service_endpoint = os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT") 
# index_name = os.getenv("AZURE_SEARCH_INDEX_NAME") 
# index_name = index_name.strip('"')
# key = os.getenv("AZURE_SEARCH_ADMIN_KEY") 
# key = key.strip('"')

import streamlit as st

openai.api_key =  st.secrets["AZURE_OPENAI_API_KEY"]
openai.api_base =  st.secrets["AZURE_OPENAI_ENDPOINT"]
openai.api_type = "azure"
emb_engine = st.secrets["AZURE_OPENAI_EMB_DEPLOYMENT"]
emb_engine = emb_engine.strip('"')

#azcs implementation
service_endpoint = st.secrets["AZURE_SEARCH_SERVICE_ENDPOINT"]
index_name = st.secrets["AZURE_SEARCH_INDEX_NAME"]
index_name = index_name.strip('"')
key = st.secrets["AZURE_SEARCH_ADMIN_KEY"]
key = key.strip('"')


# @retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(6))
# Function to generate embeddings for title and content fields, also used for query embeddings
def generate_embeddings(text):
    print("emb_engine", emb_engine)
    openai.api_version="2023-07-01-preview"
    # openai.api_version = "2023-05-15"
    response = openai.Embedding.create(
        input=text, engine=emb_engine)
    embeddings = response['data'][0]['embedding']
    return embeddings
credential = AzureKeyCredential(key)
azcs_search_client = SearchClient(service_endpoint, index_name =index_name , credential=credential)


import random
def get_weather(location):
    num = len(location)%5
    # num = random.randint(1, 5)
    if num == 1:
        print("Sunny")
        return "Sunny"
    elif num == 2:
        print("Rainy")
        return "Rainy"
    elif num == 3:
        print("Snowy")
        return "Snowy"
    elif num==4:
        print("Stormy")
        return "Stormy"
    elif num==5:
        print("Hailstorm")
        return "Hailstorm"
    else:
        print("XXXXXXXXXXXXXXXXXXXX")


def order_pizza(name, city, weather, orderlist):
    # w = get_weather(weather)

    #res = 

    print("**********Order Details***********")
    print("Customer Name : {}".format(name))
    print("Order : {}".format(orderlist))
    print("Address : ".format(city))

    order_details = {
        "name":name,
        "city":city,
        "weather":weather,
        "orderlist":orderlist
    }

    return orderlist

def search_knowledgebase(search_query):

    vector = Vector(value=generate_embeddings(search_query), k=3, fields="embedding")
    print("search query: ", search_query)
    # print("products: ", products.split(","))
    # product_filter = " or ".join([f"product eq '{product}'" for product in products.split(",")])
    results = azcs_search_client.search(  
        search_text=search_query,  
        #
        # vectors= [vector],
        # filter= product_filter,
        #
        # query_type="semantic", query_language="en-us", semantic_configuration_name='default', query_caption="extractive", query_answer="extractive",
        select=["name","finalprice","franchise","status"],
        top=3
    )  
    text_content =""
    for result in results:  
        # Needs modification for LLM to understand:
        text_content += f"{result['name']}\n{result['finalprice']}\n{result['franchise']}\n{result['status']}\n"
    # print("text_content", text_content)
    return text_content


###Sematic caching implementation
if os.getenv("USE_SEMANTIC_CACHE") == "True":
    cache_index_name = os.getenv("CACHE_INDEX_NAME")
    cache_index_name= cache_index_name.strip('"')
    azcs_semantic_cache_search_client = SearchClient(service_endpoint, cache_index_name, credential=credential)

def add_to_cache(search_query, gpt_response):
    search_doc = {
                 "id" : str(uuid.uuid4()),
                 "search_query" : search_query,
                 #
                #  "search_query_vector" : generate_embeddings(search_query),
                "gpt_response" : gpt_response
              }
    azcs_semantic_cache_search_client.upload_documents(documents = [search_doc])
def get_cache(search_query):
    #

    # vector = Vector(value=generate_embeddings(search_query), k=3, fields="search_query_vector")
    vector = Vector(value=generate_embeddings(search_query), k=3, fields="search_query")
  
    results = azcs_semantic_cache_search_client.search(  
        #
        # search_text=None,
        search_text=search_query,  
        #
        # vectors= [vector],
        select=["gpt_response"],
    )  
    try:
        result =next(results)
        print("threshold ", result['@search.score'])
        if result['@search.score']>= float(os.getenv("SEMANTIC_HIT_THRESHOLD")):
            return result['gpt_response']
    except StopIteration:
        pass

    return None


def gpt_stream_wrapper(response):
    for chunk in response:
        chunk_msg= chunk['choices'][0]['delta']
        chunk_msg= chunk_msg.get('content',"")
        yield chunk_msg


class Agent(): #Base class for Agent
    def __init__(self, engine,persona, name=None, init_message=None):
        if init_message is not None:
            init_hist =[{"role":"system", "content":persona}, {"role":"assistant", "content":init_message}]
        else:
            init_hist =[{"role":"system", "content":persona}]

        self.init_history =  init_hist
        self.persona = persona
        self.engine = engine
        self.name= name
    def generate_response(self, new_input,history=None, stream = False,request_timeout =20,api_version = "2023-07-01-preview", max_tokens=8190):
        openai.api_version = api_version
        if new_input is None: # return init message 
            return self.init_history[1]["content"]
        messages = self.init_history.copy()
        if history is not None:
            for user_question, bot_response in history:
                messages.append({"role":"user", "content":user_question})
                messages.append({"role":"assistant", "content":bot_response})
        messages.append({"role":"user", "content":new_input})
        response = openai.ChatCompletion.create(
            engine=self.engine,
            messages=messages,
            stream=stream,
            request_timeout =request_timeout
        )
        if not stream:
            return response['choices'][0]['message']['content']
        else:
            return gpt_stream_wrapper(response)
    def run(self, **kwargs):
        return self.generate_response(**kwargs)



def check_args(function, args):
    sig = inspect.signature(function)
    params = sig.parameters

    # Check if there are extra arguments
    for name in args:
        if name not in params:
            return False
    # Check if the required arguments are provided 
    for name, param in params.items():
        if param.default is param.empty and name not in args:
            return False

    return True

class Smart_Agent(Agent):
    """
    Agent that can use other agents and tools to answer questions.

    Args:
        persona (str): The persona of the agent.
        tools (list): A list of {"tool_name":tool} that the agent can use to answer questions. Tool must have a run method that takes a question and returns an answer.
        stop (list): A list of strings that the agent will use to stop the conversation.
        init_message (str): The initial message of the agent. Defaults to None.
        engine (str): The name of the GPT engine to use. Defaults to "gpt-35-turbo".

    Methods:
        llm(new_input, stop, history=None, stream=False): Generates a response to the input using the LLM model.
        _run(new_input, stop, history=None, stream=False): Runs the agent and generates a response to the input.
        run(new_input, history=None, stream=False): Runs the agent and generates a response to the input.

    Attributes:
        persona (str): The persona of the agent.
        tools (list): A list of {"tool_name":tool} that the agent can use to answer questions. Tool must have a run method that takes a question and returns an answer.
        stop (list): A list of strings that the agent will use to stop the conversation.
        init_message (str): The initial message of the agent.
        engine (str): The name of the GPT engine to use.
    """

    def __init__(self, persona,functions_spec, functions_list, name=None, init_message=None, engine =os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")):
        super().__init__(engine=engine,persona=persona, init_message=init_message, name=name)
        self.functions_spec = functions_spec
        self.functions_list= functions_list
        
    # @retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(6))
    # def run(self, user_input, conversation=None, stream = False, api_version = "2023-07-01-preview"):
    #     openai.api_version = api_version
    #     if user_input is None: #if no input return init message
    #         return self.init_history, self.init_history[1]["content"]
    #     if conversation is None: #if no history return init message
    #         conversation = self.init_history.copy()
    #     conversation.append({"role": "user", "content": user_input})
    #     i=0
    #     query_used = None

    #     while True:

    #         response = openai.ChatCompletion.create(
    #             deployment_id=self.engine, # The deployment name you chose when you deployed the GPT-35-turbo or GPT-4 model.
    #             messages=conversation,
    #         functions=self.functions_spec,
    #         function_call="auto"
            
    #         )
    #         response_message = response["choices"][0]["message"]


    #             # Step 2: check if GPT wanted to call a function
    #         if  response_message.get("function_call"):
    #             print("Recommended Function call:")
    #             print(response_message.get("function_call"))
    #             print()
                
    #             # Step 3: call the function
    #             # Note: the JSON response may not always be valid; be sure to handle errors
                
    #             function_name = response_message["function_call"]["name"]
                
    #             # verify function exists
    #             if function_name not in self.functions_list:
    #                 raise Exception("Function " + function_name + " does not exist")
    #             function_to_call = self.functions_list[function_name]  
                
    #             # verify function has correct number of arguments
    #             function_args = json.loads(response_message["function_call"]["arguments"])

    #             if check_args(function_to_call, function_args) is False:
    #                 raise Exception("Invalid number of arguments for function: " + function_name)
    #             search_query = function_args["search_query"]
    #             print("search_query", search_query)

    #             # check if there's an opprotunity to use semantic cache
    #             if function_name =="search_knowledgebase":
    #                 if os.getenv("USE_SEMANTIC_CACHE") == "True":
                        
    #                     cache_output = get_cache(search_query)
    #                     if cache_output is not None:
    #                         print("semantic cache hit")
    #                         conversation.append({"role": "assistant", "content": cache_output})
    #                         return False, query_used,conversation, cache_output
    #                     else:
    #                         print("semantic cache missed")
    #                         query_used = search_query


    #             function_response = function_to_call(**function_args)
    #             print("Output of function call:")
    #             print(function_response)
    #             print()

                
    #             # Step 4: send the info on the function call and function response to GPT
                
    #             # adding assistant response to messages
    #             conversation.append(
    #                 {
    #                     "role": response_message["role"],
    #                     "name": response_message["function_call"]["name"],
    #                     "content": response_message["function_call"]["arguments"],
    #                 }
    #             )

    #             # adding function response to messages
    #             conversation.append(
    #                 {
    #                     "role": "function",
    #                     "name": function_name,
    #                     "content": function_response,
    #                 }
    #             )  # extend conversation with function response
    #             continue
    #         else:
    #             break #if no function call break out of loop as this indicates that the agent finished the research and is ready to respond to the user

    #     if not stream:
    #         assistant_response = response_message["content"]
    #         conversation.append({"role": "assistant", "content": assistant_response})

    #     else:
    #         assistant_response = response_message

    #     return stream,query_used, conversation, assistant_response
        \

    ##
    
    # openai.api_version = "2023-07-01-preview"
    @retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(1))
    def run(self, user_input, conversation=None, stream=False, api_version="2023-07-01-preview"):
        openai.api_version = api_version
        # stream=stream
        if user_input is None:  # if no input return init message
            return self.init_history, self.init_history[1]["content"]

        if conversation is None:  # if no history return init message
            conversation = self.init_history.copy()

        conversation.append({"role": "user", "content": user_input})
        i = 0
        query_used = None

        while True:
            try:
                response = openai.ChatCompletion.create(
                    deployment_id=self.engine,
                    #
                    engine= "sagpt2",
                    messages=conversation,
                    #
                    functions=self.functions_spec,
                    function_call="auto"
                )

                # response = openai.Completion.create(
                #     engine="sagpt",
                #     prompt="",
                #     temperature=1,
                #     max_tokens=100,
                #     top_p=0.5,
                #     frequency_penalty=0,
                #     presence_penalty=0,
                #     stop=None)

                if response is None or not response.get("choices") or not response["choices"]:
                    raise Exception("Invalid response from GPT: Missing choices")

                response_message = response["choices"][0]["message"]

                # Step 2: check if GPT wanted to call a function
                if response_message.get("function_call"):
                    print("Recommended Function call:")
                    print(response_message.get("function_call"))
                    print()

                    # Step 3: call the function
                    function_name = response_message["function_call"]["name"]

                    # verify function exists
                    if function_name not in self.functions_list:
                        raise Exception("Function " + function_name + " does not exist")

                    function_to_call = self.functions_list[function_name]

                    # verify function has correct number of arguments
                    function_args = json.loads(response_message["function_call"]["arguments"])
                    #
                    print(function_args)

                    if not check_args(function_to_call, function_args):
                        raise Exception("Invalid number of arguments for function: " + function_name)

                    #
                    # search_query = function_args["search_query"]
                    # print("search_query", search_query)

                    # check if there's an opportunity to use semantic cache
                    if function_name == "search_knowledgebase" and os.getenv("USE_SEMANTIC_CACHE") == "True":
                        cache_output = get_cache(search_query)
                        if cache_output is not None:
                            print("semantic cache hit")
                            conversation.append({"role": "assistant", "content": cache_output})
                            return False, query_used, conversation, cache_output
                        else:
                            print("semantic cache missed")
                            query_used = search_query

                    function_response = function_to_call(**function_args)
                    print("Output of function call:")
                    print(function_response)
                    print()

                    # Step 4: send the info on the function call and function response to GPT
                    # adding assistant response to messages
                    conversation.append(
                        {
                            "role": response_message["role"],
                            "name": response_message["function_call"]["name"],
                            "content": response_message["function_call"]["arguments"],
                        }
                    )

                    # adding function response to messages
                    conversation.append(
                        {
                            "role": "function",
                            "name": function_name,
                            "content": function_response,
                        }
                    )  # extend conversation with function response

                    assistant_response = function_response  # Set assistant_response to the function_response

                else:
                    # if no function call break out of the loop
                    assistant_response = response_message["content"]
                    conversation.append({"role": "assistant", "content": assistant_response})
                    break

            except Exception as ex:
                print(f"Exception occurred: {ex}")
                print("Exception traceback:", traceback.format_exc())  # Add traceback information
                raise  # re-raise the exception to stop the execution

        if not stream:
            return stream, query_used, conversation, assistant_response
        else:
            return stream, query_used, conversation, response_message



# PERSONA = """
# You are Maya, a technical support specialist responsible for answering questions about computer networking and system.
# You are helping {username} with a technical question.
# You will use the search tool to find relavent knowlege articles to create the answer.
# Being smart in your research. If the search does not come back with the answer, rephrase the question and try again.
# Review the result of the search and use it to guide your next search if needed.
# If the question is complex, break down to smaller search steps and find the answer in multiple steps.
# Answer ONLY with the facts from the search tool. If there isn't enough information, say you don't know. Do not generate answers that don't use the sources below. If asking a clarifying question to the user would help, ask the question.
# Each source has a name followed by colon and the actual information, always include the source name for each fact you use in the response. Use square brakets to reference the source, e.g. [info1.txt]. Don't combine sources, list each source separately, e.g. [info1.txt][info2.pdf].
# If the user is asking for information that is not related to computer networking, say it's not your area of expertise.
# """

# PERSONA = """
# IPL (Indian Premier League) is a cricket tournament held every year in India where cricketers from all over the world participate.
# These cricketers are bought/retained/remain unsold at the IPL Auction.
# You are Jennifer, a sports specialist responsible for answering questions about the IPL Auction 2023.
# You are helping {username} with a question related to the IPL Auction 2023.
# You will use the search tool to find relavent knowledge articles to create the answer.
# Being smart in your research. If the search does not come back with the answer, rephrase the question and try again.
# Review the result of the search and use it to guide your next search if needed.
# If the question is complex, break down to smaller search steps and find the answer in multiple steps.
# Answer ONLY with the facts from the search tool. If there isn't enough information, say you don't know. Do not generate answers that don't use the sources below. If asking a clarifying question to the user would help, ask the question.
# Each source has a name followed by colon and the actual information, always include the source name for each fact you use in the response. Use square brakets to reference the source, e.g. [info1.txt]. Don't combine sources, list each source separately, e.g. [info1.txt][info2.pdf].
# If the user is asking for information that is not related to IPL Auction, say it's not your area of expertise.
# """
        
PERSONA = """
Pizza House is a leading company that offers its customers authentic pizzas and drinks.
You are Jennifer, an assistant who helps out customers to order pizza.
Get weather detials. If the weather is fine according to you, continue with the ordering procedure, else abort and inform the customer about the same in a friendly manner.
Get the required details from the customer. Ask them information in a friendly manner.
Be smart in your task completions. If the order could not be placed despite fine weather conditions, retry. Ask the customer again for some required information if it is not provided by them.
Review the order, ask the customer for their affirmation to place the order. Finally, place the order.
If you find your task complex, break it down into smaller steps.
If asking a clarifying question to the user would help, ask the question.
If the user is asking for information that is not related to ordering snacks from Pizza House, say it's not your area of expertise.
Greet the customer with a casual good bye addressing them by their name.
"""

AVAILABLE_FUNCTIONS = {
            "search_knowledgebase": search_knowledgebase,
            "order_pizza":order_pizza,
            "get_weather":get_weather
        } 

FUNCTIONS_SPEC= [  
    {
        "name": "search_knowledgebase",
        "description": "Searches the knowledge base for an answer to the technical question",
        "parameters": {
            "type": "object",
            "properties": {
                "search_query": {
                    "type": "string",
                    "description": "The search query to use to search the knowledge base"
                },

            },
            "required": ["search_query"],
        },
    },

    {
        "name": "order_pizza",
        "description": "Orders pizza for the customer.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the customer."
                },
                "city": {
                    "type": "string",
                    "description": "Order destination."
                },
                "weather": {
                    "type": "string",
                    "description": "Weather on the route between Pizza House and Order Destination."
                },
                "orderlist": {
                    "type": "string",
                    "description": "List of orders requested by the customer."
                },

            },
            "required": ["name", "city", "orderlist", "weather"],
        },
    },

    {
        "name": "get_weather",
        "description": "Gets the weather on the route between Pizza House and the Order Destination.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Location where the order needs to be delivered."
                },
            },
            "required": ["location"],
        },
    },

]  


