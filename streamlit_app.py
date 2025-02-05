import streamlit as st
from openai import OpenAI
import pandas as pd
import os
import utils.prompt_utils as prompt_utils
import openpyxl

from langchain_community.chat_models import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.prompts import PromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate, ChatPromptTemplate
from langchain_core.prompts import MessagesPlaceholder
from langchain.chains import LLMChain, ConversationChain
from langchain_core.output_parsers import StrOutputParser
from langchain.memory import ConversationBufferMemory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain.schema import AIMessage, HumanMessage
from langchain_community.chat_message_histories import StreamlitChatMessageHistory

from gcloud import storage
# from google.cloud import storage
from oauth2client.service_account import ServiceAccountCredentials
# from google.oauth2.service_account import Credentials


from models import MODEL_CONFIGS
from utils.prompt_utils import target_styles, definitions, survey_items
from utils.eval_qs import TA_0s, TA_100s
from utils.utils import response_generator
from datetime import datetime

st.set_page_config(page_title="Therapist Chatbot Evaluation", page_icon=None, layout="centered", initial_sidebar_state="expanded", menu_items=None)

# CONFIGS
style_id = 1
min_turns = 20   # number of turns to make before users can save the chat
MODEL_SELECTED = "gpt-4o"

# Show title and description.
st.title(" Therapist Chatbot Evaluation")

# Get participant ID 
user_PID = st.text_input("What is your participant ID?")

# Create a dropdown selection box
# target_style = st.selectbox('Choose a communication st:', styles)



# Retrieve api key from secrets
openai_api_key = st.secrets["OPENAI_API_KEY"]

# Initializing GCP credentials and bucket details
credentials_dict = {
        'type': st.secrets.gcs["type"],
        'client_id': st.secrets.gcs["client_id"],
        'client_email': st.secrets.gcs["client_email"],
        'private_key': st.secrets.gcs["private_key"],
        'private_key_id': st.secrets.gcs["private_key_id"],
        }
credentials = ServiceAccountCredentials.from_json_keyfile_dict(
    credentials_dict
)
# credentials = Credentials.from_service_account_info(
#     credentials_dict
# )
client = storage.Client(credentials=credentials, project='galvanic-fort-430920-e8')
bucket = client.get_bucket('streamlit-bucket-bot-eval')
file_name = 'NA'

def save_duration():
    if st.session_state["start_time"]:
        duration = datetime.now() - st.session_state["start_time"]
        st.session_state["evaluation_durations"] = duration
        # st.session_state["start_time"] = None  # Reset for the next model
    return duration

if not user_PID:
    st.info("Please enter your participant ID to start.", icon="🗝️")
         
else:
    # Display the selected option
    st.write("""**Start chatting with the AI therapist. After getting >= 10 responses from the therapist,  a 'save' button will appear. After you finished the conversation naturally,
         you may click the 'save' button to save the conversation and then fill out the evaluation questions.**""")
    # Create an OpenAI client.
    llm = ChatOpenAI(model=MODEL_SELECTED, api_key=openai_api_key)
    # llm = ChatOpenAI(model="gpt-4o-mini", api_key=openai_api_key)

    # start tracking the duration
    if 'start_time' not in st.session_state:
        st.session_state['start_time'] = datetime.now()
    if "evaluation_durations" not in st.session_state:
        st.session_state["evaluation_durations"] = None
    start_time_row = pd.DataFrame([{"role": "Start Time", "content": st.session_state['start_time']}])
        
    # therapist agent
    therapist_model_config = MODEL_CONFIGS['Therapist']
    therapyagent_prompt_template = ChatPromptTemplate.from_messages([
        ("system", therapist_model_config['prompt']),
        MessagesPlaceholder(variable_name="history"), # dynamic insertion of past conversation history
        ("human", "{input}"),
    ])
    # Communication style modifier prompt
    modifier_model_config = MODEL_CONFIGS['Modifier']
    csm_prompt_template = PromptTemplate(
        variables=["communication_style", "chat_history", "unadapted_response"], template=modifier_model_config['prompt']
    )

    # set up streamlit history memory
    msgs = StreamlitChatMessageHistory(key="chat_history")

    # Create a session state variable to store the chat messages. 
    # This ensures that the messages persist across reruns.
    if "messages" not in st.session_state:
        st.session_state.messages = [
            # Prewritten first turn
            # {"role": "user", "content": "Hello."},
            {"role": "assistant", "content": """Hello, I am an AI therapist, here to support you in navigating the challenges and emotions you may face as a caregiver. 
             Is there a specific caregiving challenge or experience you would like to share with me today?"""},
        ]

    # SIDEBAR CONTENT
    # with st.sidebar:
        # with st.expander(label='Evaluation Section 1', expanded=True):
        #     col1, col2, col3 = st.columns(3)
        #     with col1:
        #         st.write(TA_0s[0])
        #     with col2:
        #         TA_rating_1 = st.slider(label='TA_1', min_value=0, max_value=100, step=1,
        #                                 value=50, label_visibility='hidden')
        #     with col3:
        #         st.write(TA_100s[0])
        #     TA_rationale_1_pos = ''
        #     TA_rationale_1_neg = ''
        #     if TA_rating_1 < 40:
        #         TA_rationale_1_neg = st.text_input("What made you feel unheard or disrespected during the session?")
        #     if TA_rating_1 > 60:
        #         TA_rationale_1_pos = st.text_input("What did the chatbot do that made you feel especially respected and understood?")
            
        #     # TA rating 2
        #     col1, col2, col3 = st.columns(3)
        #     with col1:
        #         st.write(TA_0s[1])
        #     with col2: 
        #         TA_rating_2 = st.slider(label='TA_2', min_value=0, max_value=100, step=1,
        #                             value=50, label_visibility='collapsed')
        #     with col3:
        #         st.write(TA_100s[1])
        #     TA_rationale_2_pos = ''
        #     TA_rationale_2_neg = ''
        #     if TA_rating_2 < 40:
        #         TA_rationale_2_neg = st.text_input("What important topics or goals did you feel were missed?")
        #     if TA_rating_2 > 60:
        #         TA_rationale_2_pos = st.text_input("What made this session particularly focused and relevant to your needs?")
            
        #     # TA rating 3
        #     col1, col2, col3 = st.columns(3)
        #     with col1:
        #         st.write(TA_0s[2])
        #     with col2: 
        #         TA_rating_3 = st.slider(label='TA_3', min_value=0, max_value=100, step=1,
        #                             value=50, label_visibility='collapsed')
        #     with col3:
        #         st.write(TA_100s[2])
        #     TA_rationale_3_pos = ''
        #     TA_rationale_3_neg = ''
        #     if TA_rating_3 < 40:
        #         TA_rationale_3_neg = st.text_input("What about the chatbot's approach didn't work well for you?")
        #     if TA_rating_3 > 60:
        #         TA_rationale_3_pos = st.text_input("What aspects of the chatbot's approach were especially helpful?")
            
        #      # TA rating 4
        #     col1, col2, col3 = st.columns(3)
        #     with col1:
        #         st.write(TA_0s[3])
        #     with col2: 
        #         TA_rating_4 = st.slider(label='TA_4', min_value=0, max_value=100, step=1,
        #                             value=50, label_visibility='collapsed')
        #     with col3:
        #         st.write(TA_100s[3])
        #     TA_rationale_4_pos = ''
        #     TA_rationale_4_neg = ''
        #     if TA_rating_4 < 40:
        #         TA_rationale_4_neg = st.text_input("What were the main things that made this session unsatisfactory?")
        #     if TA_rating_4 > 60:
        #         TA_rationale_4_pos = st.text_input("What made this session particularly valuable for you?")

        # with st.expander(label='Evaluation Section 2', expanded=False):
        #     st.write('How much would you like to continue working with the chatbot in the future?')
        #     col1, col2, col3 =st.columns(spec=[0.2,0.6,0.2],gap='small',vertical_alignment="top")
        #     with col1:
        #         st.write('Not at all')
        #     with col2:
        #         UE_rating_1 = st.slider(label='EU_1', min_value=0, max_value=10, step=1,
        #                                 value=5,label_visibility="collapsed")
        #     with col3:
        #         st.write('Very much')
            
        #     st.write('How likely are you to recommend this chatbot to others?')
        #     col1, col2, col3 =st.columns(spec=[0.2,0.6,0.2],gap='small',vertical_alignment="top")
        #     with col1:
        #         st.write('Not likely at all')
        #     with col2:
        #         UE_rating_2 = st.slider(label='EU_2', min_value=0, max_value=10, step=1,
        #                                 value=5,label_visibility="collapsed")
        #     with col3:
        #         st.write('Extremely likely')

        
        # with st.expander(label='Evaluation Section 3', expanded=False):
        #     st.write('To what extent did the chatbot express warmth and care towards you?')
        #     col1, col2, col3 =st.columns(spec=[0.2,0.6,0.2],gap='small',vertical_alignment="top")
        #     with col1:
        #         st.write("Not at all")
        #     with col2:
        #         Empathy_rating_1 = st.slider(label='EMP_1', min_value=0, max_value=100, step=1,
        #                                 value=50,label_visibility="collapsed")
        #     with col3:
        #         st.write("A great deal")
            
        #     st.write('How accurately did the chatbot reflect your feelings and experiences back to you?')
        #     col1, col2, col3 =st.columns(spec=[0.2,0.6,0.2],gap='small',vertical_alignment="top")
        #     with col1:
        #         st.write("Not at all")
        #     with col2:
        #         Empathy_rating_2 = st.slider(label='EMP_2', min_value=0, max_value=100, step=1,
        #                                 value=50,label_visibility="collapsed")
        #     with col3:
        #         st.write("Extremely accurate")
                
        #     st.write('How well did the chatbot help you explore feelings you hadn\'t initially expressed?')
        #     col1, col2, col3 =st.columns(spec=[0.2,0.6,0.2],gap='small',vertical_alignment="top")
        #     with col1:
        #         st.write("Not at all")
        #     with col2:
        #         Empathy_rating_3 = st.slider(label='EMP_3', min_value=0, max_value=100, step=1,
        #                                 value=50,label_visibility="collapsed")
        #     with col3:
        #         st.write("Very well")
        

        # st.write('If you have not saved your conversation yet, please make sure to save your conversation before you save your ratings.')
        # exit_ind = 0
        # if st.button('Save ratings'): exit_ind = 1

        # if exit_ind == 1:

        #     ratings_data = {
        #         'aspect': ['TA_rating_1', 'TA_rating_2', 'TA_rating_3','TA_rating_4','TA_rationale_1_pos', 'TA_rationale_2_pos', 
        #                    'TA_rationale_3_pos', 'TA_rationale_4_pos',
        #                    'TA_rationale_1_neg', 'TA_rationale_2_neg', 'TA_rationale_3_neg', 'TA_rationale_4_neg',
        #                    'UE_rating_1','UE_rating_2',
        #                    'Empathy_rating_1','Empathy_rating_2','Empathy_rating_3'],
        #         'rating': [TA_rating_1, TA_rating_2, TA_rating_3,TA_rating_4,
        #                    TA_rationale_1_pos, TA_rationale_2_pos, TA_rationale_3_pos, TA_rationale_4_pos,
        #                    TA_rationale_1_neg, TA_rationale_2_neg, TA_rationale_3_neg, TA_rationale_4_neg,
        #                    UE_rating_1,UE_rating_2,
        #                    Empathy_rating_1,Empathy_rating_2,Empathy_rating_3]
        #     }
        #     ratings_df = pd.DataFrame(ratings_data)
            
        #     # ratings_file_name = "EvalRatings_Unadapted_P{PID}.csv".format(PID=user_PID)
        #     ratings_file_name = "EvalRatings_{style}_P{PID}.csv".format(style=target_styles[style_id], PID=user_PID)
        #     ratings_df.to_csv(ratings_file_name, index=False)
        #     blob = bucket.blob(ratings_file_name)
        #     blob.upload_from_filename(ratings_file_name)
        #     st.write("**Evaluation ratings was uploaded successfully.**")


        # add_selectbox = st.selectbox(
        #     "How would you like to be contacted?",
        #     ("Email", "Home phone", "Mobile phone")
        # )

        # add_selectbox_2 = st.selectbox(
        #     "How would you rate the chatbot",
        #     ("Email", "Home phone", "Mobile phone")
        # )

    # Display the existing chat messages via `st.chat_message`.
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


    chat_history_df = pd.DataFrame(st.session_state.messages)
    
    # Create a chat input field to allow the user to enter a message. This will display
    # automatically at the bottom of the page.
    if user_input := st.chat_input("Enter your input here."):
        
        # Create a therapy chatbot llm chain
        therapyagent_chain = therapyagent_prompt_template | llm
        therapy_chain_with_history = RunnableWithMessageHistory(
            therapyagent_chain,
            lambda session_id: msgs,  # Always return the instance created earlier
            input_messages_key="input",
            # output_messages_key="content",
            history_messages_key="history",
        )

        # create a csm chain
        csmagent_chain = LLMChain(
            llm=llm,
            prompt=csm_prompt_template,
            verbose=False,
            output_parser=StrOutputParser()
        )

        # Store and display the current prompt.
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        config = {"configurable": {"session_id": "any"}}
        unada_response = therapy_chain_with_history.invoke({"input": user_input}, config)
        unada_bot_response = unada_response.content

        target_style = target_styles[style_id]
        definition = definitions[style_id]
        survey_item = survey_items[style_id]
        ada_response = csmagent_chain.predict(communication_style=target_style,
                                            definition=definition,
                                            survey_item=survey_item,
                                            unadapted_chat_history= st.session_state.messages,
                                            unadapted_response=unada_bot_response)

        # Stream the response to the chat using `st.write_stream`, then store it in 
        # session state.
        with st.chat_message("assistant"):
            response = st.write_stream(response_generator(response = ada_response))

        st.session_state.messages.append({"role": "assistant", "content": ada_response})
        chat_history_df = pd.DataFrame(st.session_state.messages)

    # automatically save the conversation after reaching the minimum turns (e.g. 10)
    if chat_history_df.shape[0]>=min_turns or (user_input=="SAVE" or user_input=="save" or user_input=="STOP" or user_input=="stop"):
        # file_name = "Unadapted_P{PID}.csv".format(PID=user_PID)
        file_name = "{style}_P{PID}.csv".format(style=target_styles[style_id], PID=user_PID)
        # st.write("file name is "+file_name)

        end_time_row = pd.DataFrame([{"role": "End Time", "content": datetime.now()}])
        duration_row = pd.DataFrame([{"role": "Duration", "content": save_duration()}])
        # Append the time rows
        chat_history_df = pd.concat([chat_history_df, start_time_row, end_time_row, duration_row], ignore_index=True)
        
        chat_history_df.to_csv(file_name, index=False)
        
        blob = bucket.blob(file_name)
        blob.upload_from_filename(file_name)

        if st.button("Save Conversation & Start Evaluation"):
            st.write("**Chat history is saved successfully. You can begin filling out the evaluation questions now.**")

        # csv = chat_history_df.to_csv()
        # st.download_button(
        #     label="Click here to also download a local copy of your chat history.",
        #     data=csv,
        #     file_name=file_name,
        #     mime="text/csv",
        # )
