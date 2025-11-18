
import streamlit as st
# import asyncio
# from rasa.core.agent import Agent

# # Load the trained Rasa model
# # Note: This is commented out because the current Python version (3.12) is not compatible with the
# # specified version of rasa. To use this, you will need to use a Python version < 3.11.
# # model_path = "models"
# # agent = Agent.load(model_path)

st.title("Rasa Chatbot")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# React to user input
if prompt := st.chat_input("What is up?"):
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # # Get response from Rasa model
    # # Note: This is commented out because the current Python version (3.12) is not compatible with the
    # # specified version of rasa. To use this, you will need to use a Python version < 3.11.
    # async def get_rasa_response(message):
    #     return await agent.handle_text(message)
    #
    # response_data = asyncio.run(get_rasa_response(prompt))
    # response = response_data[0]['text'] if response_data else "Sorry, I didn't understand that."

    # Echo bot fallback
    response = f"Echo: {prompt}"


    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        st.markdown(response)
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": response})
