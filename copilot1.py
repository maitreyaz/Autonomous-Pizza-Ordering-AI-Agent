import streamlit as st
from streamlit_extras.add_vertical_space import add_vertical_space
from utils1 import PERSONA, AVAILABLE_FUNCTIONS, FUNCTIONS_SPEC, Smart_Agent, add_to_cache
import sys
import time
import random
import os
from pathlib import Path  
import json
with open('./user_profile.json') as f:
    user_profile = json.load(f)
functions = FUNCTIONS_SPEC.copy()
# functions[0]["parameters"]["properties"]["products"]["description"] = functions[0]["parameters"]["properties"]["products"]["description"].format(products=user_profile['products'])

agent = Smart_Agent(persona=PERSONA.format(username=user_profile['username']),functions_list=AVAILABLE_FUNCTIONS, functions_spec=functions, init_message=f"Hi {user_profile['username']}, this is Jennifer, your assistant for ordering delicious food from Pizza House. What would you order today?", engine="sagpt2")
# agent = Smart_Agent(persona=PERSONA.format(username=user_profile['username']),functions_list=AVAILABLE_FUNCTIONS, functions_spec=functions, init_message=f"Hi {user_profile['username']}, this is Jennifer, your IPL Auction 2023 Guide. What can I do for you?", engine="sagpt2")

# st.set_page_config(layout="wide",page_title="Enterprise Copilot- A demo of Copilot application using GPT")
st.set_page_config(layout="wide",page_title="PizzaHaus")
styl = f"""
<style>
    .stTextInput {{
      position: fixed;
      bottom: 3rem;
    }}
</style>
"""
st.markdown(styl, unsafe_allow_html=True)


MAX_HIST= 5
# Sidebar contents
with st.sidebar:
    st.title('Tech Copilot')
    st.markdown('''
    Indulge in Authentic Italian Flavor at PizzaHaus - Where Every Slice is a Taste of Italy!

    ''')
    add_vertical_space(5)
    st.write('Your Assistant : Ms. Jennifer')
    if st.button('Clear Chat'):

        if 'history' in st.session_state:
            st.session_state['history'] = []

    if 'history' not in st.session_state:
        st.session_state['history'] = []
    if 'input' not in st.session_state:
        st.session_state['input'] = ""


user_input= st.chat_input("You:")

## Conditional display of AI generated responses as a function of user provided prompts
history = st.session_state['history']
      
if len(history) > 0:
    for message in history:
        if message.get("role") != "system" and message.get("name") is  None:
            with st.chat_message(message["role"]):
                    st.markdown(message["content"])
else:
    history, agent_response = agent.run(user_input=None)
    with st.chat_message("assistant"):
        st.markdown(agent_response)
    user_history=[]
if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)
    stream_out, query_used, history, agent_response = agent.run(user_input=user_input, conversation=history, stream=False)
    with st.chat_message("assistant"):
        if stream_out:
            message_placeholder = st.empty()
            full_response = ""
            for response in agent_response:
                if len(response.choices)>0:
                    full_response += response.choices[0].delta.get("content", "")
                    message_placeholder.markdown(full_response + "▌")
            message_placeholder.markdown(full_response)
            if query_used: #add to cache
                add_to_cache(query_used, full_response)
                print(f"query {query_used} added to cache")
            history.append({"role": "assistant", "content": full_response})
        else:
            st.markdown(agent_response)

st.session_state['history'] = history
