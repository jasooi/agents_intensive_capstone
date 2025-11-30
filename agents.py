
"""
This file defines all agents and tools used in main.py

This system basically comprises of 2 sections
First section - the content brief is prepared. 
"""
import os
# Set API key env var in terminal: export GOOGLE_MAPS_API_KEY="YOUR_ACTUAL_KEY"
#google_maps_api_key = os.environ.get("GOOGLE_MAPS_API_KEY")

os.environ["GOOGLE_API_KEY"] = "REDACTED"

# Import relevant packages
from google.genai import types
from google.adk.agents import Agent
from google.adk.tools import AgentTool, FunctionTool, google_search
from google.adk.tools.tool_context import ToolContext
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
import asyncio

import base64
from email.message import EmailMessage
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow


# Create clarifier agent
clarifier = Agent(
    name="clarifier",
    model="gemini-2.5-flash-lite",
    description="An agent who asks the human user questions.",
    instruction="""You are an expert in communications. You work in a team whose aim is to write an email on behalf of a human user. 
    Your job is to ask questions to ensure that the email writer has all the details they need to write a good email.

    Read what the user says and identify the feeling that they are most likely feeling. 
    The user may express anger, sadness, sarcasm, gratefulness, uncertainty or even bittersweet feelings, for example.
    If the user is talking in a sarcastic or dismissive manner, match their energy. Otherwise,
    ask your questions in a friendly and empathetic tone. Ask one question at a time.

    An example of a good response: "You mentioned that you're not sure what you would like to tell your ex. Did you part on bad terms?"
    Another example of a good response: "I understand that it must have been a difficult time for you. How long ago did you leave the company?"
    
    An example of a bad response: "What else do you have to say to them?"
    
    """,
)


# Create content brief drafter agent
content_brief_drafter = Agent(
    name="content_brief_drafter",
    model="gemini-2.5-flash-lite",
    description="A content brief writer agent.",
    instruction="""You are an experienced content brief writer. 
    You work in a team whose aim is to write an email on behalf of a human user.
    Your job is to write structured email content briefs which will then help your teammates
    write good emails. Based on all the information and feedback the human user has shared with the team,
    identify the objective, tone, target audience and message of the email.

    You may use the google_search tool to search up references that are outside your domain of knowledge.
    
    Follow the below format for your content brief.
    
    --CONTENT BRIEF--
    Target audience of Email: Brief description of the person this email is intended for. Include relationship to the human user and how long ago did their relationship end. (e.g. Rob, former lover, broke up 3 months ago)
    Objective of Email: Brief summary of the intended outcome of this email. (e.g. To convey an amicable farewell)
    Tone: Describe the desired emotional tone of the email and stylistic choices. (e.g. familiar but polite, bittersweet)
    Message: Numbered bullet points of the main content the email should cover. (e.g. 1. Apologise for not being available often 2. Wish the reader a good life)
    
    """,
    tools=[google_search],
    output_key="latest_content_brief",
)

# Create email drafter agent
email_drafter = Agent(
    name="email_drafter",
    model="gemini-2.5-flash-lite",
    description="An agent who writes emails.",
    instruction="""You are an agent who helps the user write emails. 
    You work in a team whose aim is to write an email on behalf of a human user.
    Based on the latest content brief, write an email draft. Use the `google_search` tool to ground
    your references, if there is anything you are unsure about.

    Expected Output Format in JSON:
    {"Sender": "Sender email address here",
    "Recipient": "Recipient email address here",
    "Title" : "Your email title here",
    "Body": "Your email draft here"}

    Do not output any additional text.
    """,
    tools=[google_search],
    output_key="email_draft",
)

# Create email editor agent
email_editor = Agent(
    name="email_editor",
    model="gemini-2.5-flash-lite",
    description="An agent who edits emails.",
    instruction="""You are a constructive critic.  
    You work in a team whose aim is to write an email on behalf of a human user.
    Based on the latest content brief, review the email draft provided below.

    Email Draft:
    {email_draft}

    Evaluate the email draft's relevance, completeness and tone appropriateness.
    - If the email is well-written and complete, you MUST respond with the exact phrase: "APPROVED"
    - Otherwise, provide 2-3 specific, actionable suggestions for improvement.
    """,
    output_key="feedback",
)

# Define finalise email tool
def finalise_email()->dict:
    """Call this function ONLY when the email draft is 'APPROVED',
      which indicates that the email is good to go,
      and no more changes are needed."""
    return {"status": "approved", "message": "Email is approved. Exiting refinement loop."}

# Create email refiner agent
email_refiner = Agent(
    name="email_refiner",
    model="gemini-2.5-flash-lite",
    description="An agent who rewrites emails based on feedback.",
    instruction="""You are an email refiner.  You have an email draft and the feedback on it.

    Email Draft:
    {email_draft}

    Feedback:
    {feedback}

    Your task is to analyze the feedback.
    - IF the critique is EXACTLY "APPROVED", you MUST call the `finalise_email` function and nothing else.
    - OTHERWISE, rewrite the email draft to fully incorporate the feedback in the appropriate format.

    Expected Output Format in JSON:
    {"Sender": "Sender email address here",
    "Recipient": "Recipient email address here",
    "Title" : "Your email title here",
    "Body": "Your email draft here"}

    Do not output any additional text.
    """,
    output_key= "email_draft",
    tools=[
        FunctionTool(finalise_email)
    ],
)

# # Create loop agent structure
# # Basically the initial email written by the email editor agent will be iteratively refined by the email editor and refiner agents
# email_refinement_loop = LoopAgent(
#     name="EmailRefinementLoop",
#     sub_agents=[email_editor, email_refiner],
#     max_iterations=3,  # Prevents infinite loops
# )

# # Nest the loop structure within a sequential pipeline for email writing
# email_pipeline = SequentialAgent(
#     name="EmailPipeline",

#     sub_agents=[email_drafter, email_refinement_loop],
# )

# Create the send email custom function tool
# First, define constants for gmail API client
CLIENT_SECRETS_FILE = 'C://Users//Jasmine//Downloads//client_secret_930781233976-9onhmjdavne0tauh929h662e1uqmt2g0.apps.googleusercontent.com.json'
SCOPES = ['https://www.googleapis.com/auth/gmail.compose']
API_SERVICE_NAME = 'gmail'
API_VERSION = 'v1'

# Then, define helper function to create connection
def get_authenticated_service():
    # Load credentials from local client secret JSON downloaded from GCloud console
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)

    # Run local OAuth
    credentials = flow.run_local_server()
    return build(API_SERVICE_NAME, API_VERSION, credentials = credentials)

# Finally, define function that sends an email on behalf of the user (via OAuth)
def send_email(message_title:str, message_body:str, sender:str, recipient:str)->str:
    """
    This tool creates and sends an email message based on the provided arguments.

    Args: 
    `message_title` which is the title of the email, 
    `message_body` which is the body text of the email,
    `sender` which is the email address of the user,
    `recipient` which is the email address this email is to be addressed to

    Output:
    string describing the send status of the email

    """
    try:
        # Create gmail API client
        service = get_authenticated_service()

        # Create message using provided inputs
        message = EmailMessage()
        message.set_content(message_body)
        message["To"] = recipient
        message["From"] = sender
        message["Subject"] = message_title
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"raw": encoded_message}
        email = (
            service.users().messages().send(userId="me", body=create_message).execute()
        )

        # Verify that email has been successfully created
        print(f"Message ID = {email["id"]}")

    except HttpError as error:
        print(f"Email sending not successful, refer to error message:\n {error}")
        email = None
        return "Email failed to send. Ask user for valid email and/or check that email has appropriate permissions."

    return f"Email successfully sent with email ID {email["id"]}"


# Create root agent... AKA the big mastermind
root_agent = Agent(
    name="master",
    model="gemini-2.5-flash-lite",
    description="An agent that helps the human user to write an email.",
    instruction= """You manage a team that writes an email on behalf of the human user. 
    Your goal is to write an email that accurately captures the human user's intended sentiment and message to their target audience, who is someone they no longer talk to.

    You are chatting with the human user. Use a friendly and empathetic tone, as if you were a close friend of the user.
    You MUST follow the below steps:
    1) Judge if you have information about the intended purpose, target audience, desired tone of the email from the user.
    2) If you do not have any of the above information, call the `clarifier` agent to ask questions to get the necessary information. 
    3) Call the `content_brief_drafter` agent to create an email content brief.  
    4) Show the content brief to the user and ask for their feedback. DO NOT skip this step.
    5) If there is feedback from the user on the content brief, call the `content_brief_drafter` agent to write a new brief based on the feedback. 
    6) Repeat steps 4 and 5 until the user clearly says they approve of the content brief
    7) After you get approval from the user, ask the user for the sender and recipient email addresses
    8) With the sender and recipient details, call the `email_drafter` sub-agent to write the initial email draft. This agent will produce an output called `email_draft` which is a JSON containing the sender, recipient, title and body of the email.
    9) Then, call the `email_editor` agent to give suggestions to improve the email draft
    10) Then call the `email_refiner` agent to refine the draft email based on the suggestions 
    11) Show the draft email to the user and get their approval to send the email. NEVER skip this step!
    12) If there is feedback from the user on the email draft, repeat steps 9, 10 and 11 until you get approval from the user
    13) Only when you get explicit approval from the user, use the `send_email` tool to send the email

    """,
    # sub_agents=[email_pipeline],
    tools=[AgentTool(clarifier),
           AgentTool(content_brief_drafter),
           AgentTool(email_drafter),
           AgentTool(email_editor),
           AgentTool(email_refiner),
           FunctionTool(send_email)
           ],
)

# Define main function with async keyword, since we need to use await for the LLM response
# TODO: test context variable issue
async def main():
    # Set the details of the app and session
    APP_NAME = 'to_all_the_exes_ive_maybe_loved_before'
    SESSION_ID = '12345'
    USER_ID = 'jasmine'

    # Start session service and create session object
    session_memory_service = InMemorySessionService()
    example_session = await session_memory_service.create_session(app_name=APP_NAME, session_id=SESSION_ID, user_id=USER_ID)

    # Create session runner (only need 1 since same app and session service)
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_memory_service)
    
    # Create loop breaker and counter variables
    is_convo_end = False
    iter_count = 0

    # Looping logic for ongoing conversation
    print("Please tell me what would you like to email your ex (lover/boss/friend/anyone, really):")
    while is_convo_end == False:
        user_prompt = input("Your response: ")

        if user_prompt == "END" or iter_count == 16:
            is_convo_end = True
            break
        else:
            # Format user query in ADK Content format
            user_prompt_formatted = types.Content(role='user', parts=[types.Part(text=user_prompt)])
            
            # run agentic system
            async for event in runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=user_prompt_formatted):
                if event.is_final_response() and event.content and event.content.parts:
                    final_response_text = event.content.parts[0].text
                    print(f'Agent response: {final_response_text}')
                    break

                
    return 0

# Run the async main function
if __name__ == "__main__":
    asyncio.run(main())







