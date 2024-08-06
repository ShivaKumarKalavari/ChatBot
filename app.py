from fastapi import FastAPI, Request, File, UploadFile, HTTPException, Form, Response, Depends
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
from starlette.status import HTTP_200_OK
import random
import json
import os
import re
import requests
from difflib import SequenceMatcher

app = FastAPI()

templates = Jinja2Templates(directory="templates")

GREET_INPUTS = ("hello", "hi", "greetings", "sup", "what's up", "hey")
GREET_RESPONSES = ["hi", "hey", "*nods*", "hi there", "hello", "I am glad! You are talking to me"]
EXIT_RESPONSES = ["Bye", "See you later!", "Good bye!", "Hope to see you again"]

previous_question = ""
previous_response = ""

feedback_file_path = "supervised_learning.txt"
comments_file = "comments.txt"

with open("dataset.json", "r") as file:
    dataset = json.load(file)

def greet(sentence):
    for word in sentence.split():
        if word.lower() in GREET_INPUTS:
            return random.choice(GREET_RESPONSES)

CONVERSATION_FILE_PATH = "conversations.json"
def load_conversations():
    with open(CONVERSATION_FILE_PATH, "r") as conversation_file:
        return json.load(conversation_file)["conversations"]

no_counter = 0
max_no_count = 3

def generate_response(user_input):
    global previous_question, previous_response, dataset, no_counter

    print(f"Received user input: {user_input}")  # Add this line for debugging

    if user_input.lower() in GREET_INPUTS:
        return greet(user_input) + "."

    if user_input.lower() in ["bye", "see you later"]:
        return random.choice(EXIT_RESPONSES)

    def process_feedback_lines(feedback_lines, threshold):
        for i in range(0, len(feedback_lines), 4):
            stored_user_message = feedback_lines[i].strip().replace("User Message: ", "")
            stored_bot_response = feedback_lines[i + 1].strip().replace("Bot Response: ", "")
            similarity_ratio = SequenceMatcher(None, user_input.lower(), stored_user_message.lower()).ratio()

            if similarity_ratio >= threshold:
                if stored_bot_response[-1] in ["!", "."]:
                    if "<" in stored_bot_response:
                        return stored_bot_response
                    elif "/" in stored_bot_response:
                        stored_bot_response = stored_bot_response.replace("/", "<br>\u2022")
                    return stored_bot_response
                else:
                    if "<" in stored_bot_response:
                        return stored_bot_response
                    elif "/" in stored_bot_response:
                        stored_bot_response = stored_bot_response.replace("/", "<br>\u2022")
                    return stored_bot_response + "."
        return None

    SIMILARITY_THRESHOLDS = [1.0, 0.9, 0.8]  # Adjust these as needed

    with open(feedback_file_path, "r", encoding="utf-8") as feedback_file:
        feedback_lines = feedback_file.readlines()

        for threshold in SIMILARITY_THRESHOLDS:
            result = process_feedback_lines(feedback_lines, threshold)
            if result:
                return result

    user_queries_to_bot_responses = {}

    # Iterate through the sub-dictionaries under the "software" key
    for sub_topic, sub_data in dataset["software"].items():
        user_queries = sub_data.get("user_queries", [])
        bot_responses = sub_data.get("bot_responses", [])

        key_value_pairs = dict(zip(user_queries, bot_responses))
        user_queries_to_bot_responses.update(key_value_pairs)

    def get_best_match(query, query_dict, threshold=0.8):
        best_match = None
        best_ratio = 0

        for stored_query in query_dict:
            ratio = SequenceMatcher(None, query.lower(), stored_query.lower()).ratio()
            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_match = stored_query
        return best_match

    for subroot in dataset:
        subroot_data = dataset[subroot]
        current_data = subroot_data

        keywords = user_input.lower().split()
        for keyword in keywords:
            if keyword in current_data:
                current_data = current_data[keyword]

        if "bot_responses" in current_data:
            return random.choice(current_data["bot_responses"])

    best_match = get_best_match(user_input, user_queries_to_bot_responses)
    if best_match and best_match in user_queries_to_bot_responses:
        return user_queries_to_bot_responses[best_match]

    current_data = dataset
    keywords = user_input.lower().split()
    for keyword in keywords:
        if keyword in current_data:
            current_data = current_data[keyword]

    if "bot_responses" in current_data:
        return random.choice(current_data["bot_responses"])

    conversations = load_conversations()

    for entry in conversations:
        pattern = entry['user_input']
        if re.match(pattern, user_input, re.IGNORECASE):
            # Reset the counter after providing a response
            no_counter = 0
            if '{user_input}' in entry.get('bot_response', ''):
                return entry['bot_response'].replace('{user_input}', user_input)
            else:
                return entry.get('bot_response', '')

    negative_patterns = [".*\\bno\\b.*", ".*\\bnever\\b.*"]
    if any(re.match(pattern, user_input, re.IGNORECASE) for pattern in negative_patterns):
        no_counter += 1
        if no_counter < max_no_count:
            return "No worries! Is there anything else you'd like to talk about or ask?"
        else:
            no_counter = 0
            return "It seems we're stuck on a loop. If there's anything specific you'd like to discuss, feel free to let me know."
    no_counter = 0

    return "I couldn't find information related to your question."

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/join")
def join(request: Request):
    return templates.TemplateResponse("join.html", {"request": request})

def save_user_data(name, email, phone, resume, city, pincode, message):
    user_folder = os.path.join('userdata', name)

    # Create a folder for each user if it doesn't exist
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)

    # Save user information in a text file
    with open(os.path.join(user_folder, 'info.txt'), 'w', encoding="utf-8") as info_file:
        info_file.write(f"Name: {name}\n")
        info_file.write(f"Email: {email}\n")
        info_file.write(f"Phone: {phone}\n")
        info_file.write(f"City: {city}\n")
        info_file.write(f"Pincode: {pincode}\n")
        info_file.write(f"Message: {message}\n")

    # Save the resume file
    with open(os.path.join(user_folder, 'resume.pdf'), 'wb') as resume_file:
        resume_file.write(resume)

@app.post("/submit_join_form")
async def submit_join_form(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    resume: UploadFile = File(...),
    city: str = Form(...),
    pincode: str = Form(...),
    message: str = Form(...),
):
    # Convert the file content to bytes
    resume_bytes = await resume.read()

    # Store user data
    save_user_data(name, email, phone, resume_bytes, city, pincode, message)

    return "Thank you for joining our App Development Community!\nYour data has been submitted successfully.\nPlease wait for a while; we will respond to you via phone or email."

@app.get("/tutorial")
def tutorial(request: Request):
    return templates.TemplateResponse("tutorial.html", {"request": request})

@app.get("/bot")
def tutorial(request: Request):
    return templates.TemplateResponse("chatbot.html", {"request": request})

@app.get("/details")
def details(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})

@app.get("/login")
def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/history")
def history(request: Request):
    return templates.TemplateResponse("history.html", {"request": request})

@app.get("/logout")
def logout(request: Request):
    return templates.TemplateResponse("logout.html", {"request": request})


@app.post("/submit_form")
async def submit_form(request: Request):
    try:
        form_data = await request.form()
        name = form_data.get('name')
        email = form_data.get('email')
        message = form_data.get('message')

        if name and email and message:
            with open("form_data.txt", "a", encoding="utf-8") as file:
                file.write(f"Name: {name}\nEmail: {email}\nMessage: {message}\n\n")


            return Response("Data submitted successfully! We will respond soon.")

        return Response("Data submission failed.")

    except Exception as e:
        return Response(f"Internal Server Error. {e}")

@app.post("/send_message")
async def send_message(request: Request):
    user_message = (await request.form()).get('user_message')

    if user_message.lower().startswith("feedback:"):
        feedback = user_message[len("feedback:"):].strip()
        # Process the feedback
        if feedback:
            # Save the feedback to the drawbacks.txt file
            with open("drawbacks.txt", "a", encoding="utf-8") as drawbacks_file:
                drawbacks_file.write(feedback + "\n")
            # Respond with a confirmation message
            return JSONResponse(content={"bot_response": "Thank you for your feedback."})

    if user_message.lower() in ['thanks', 'thank you']:
        bot_response = "You are welcome."
    else:
        bot_response = generate_response(user_message)

    global um
    um = user_message

    return JSONResponse(content={"bot_response": bot_response})

data_directory = "data"  # Directory to store user data files

@app.post("/signup")
async def signup(request: Request):
    data = await request.json()
    username = data.get('username')
    password = data.get('password')
    secret_key = data.get('password')

    if username and password:
        # Generate a secret key

        # Store user data in a text file
        user_data = f"Username: {username}, Password: {password}, Secret Key: {secret_key}"
        file_path = os.path.join(data_directory, f"{username}.txt")
        with open(file_path, "w", encoding="utf-8") as user_file:
            user_file.write(user_data)

        return JSONResponse(content={"message": "Registration successful"})
    else:
        return JSONResponse(content={"message": "Invalid input"}, status_code=400)

@app.get("/check_user")
async def check_user(username: str):
    if username:
        file_path = os.path.join(data_directory, f"{username}.txt")
        user_exists = os.path.exists(file_path)
        return JSONResponse(content={"exists": user_exists})
    else:
        return JSONResponse(content={"exists": False})

@app.post("/create_user")
async def create_user(request: Request):
    data = await request.json()
    username = data.get('username')
    password = data.get('password')
    secret_key = data.get('secretKey')

    if username and password and secret_key:
        # Store user data in a text file
        user_data = f"Username: {username}, Password: {password}, Secret Key: {secret_key}"
        file_path = os.path.join(data_directory, f"{username}.txt")
        with open(file_path, "w", encoding="utf-8") as user_file:
            user_file.write(user_data)

        return JSONResponse(content={"message": "User creation successful"})
    else:
        return JSONResponse(content={"message": "Invalid input"}, status_code=400)

@app.post("/loginuser")
async def loginuser(request: Request):
    data = await request.json()
    username = data.get('username')
    password = data.get('password')

    if username and password:
        file_path = os.path.join(data_directory, f"{username}.txt")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as user_file:
                user_data = user_file.read()
                if f"Username: {username}, Password: {password}" in user_data:
                    return JSONResponse(content={"message": "Login successful"})

        return JSONResponse(content={"message": "Invalid login credentials"}, status_code=401)
    else:
        return JSONResponse(content={"message": "Invalid input"}, status_code=400)

@app.post("/reset_password")
async def reset_password(request: Request):
    data = await request.json()
    username = data.get('username')
    secret_key = data.get('secret_key')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')

    if (
        username == "" or
        secret_key == "" or
        new_password == "" or
        confirm_password == ""
    ):
        return JSONResponse(content={"message": "Please fill all fields!"}, status_code=400)

    if username and secret_key and new_password and confirm_password:
        file_path = os.path.join(data_directory, f"{username}.txt")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as user_file:
                user_data = user_file.read()
                stored_secret_key = re.search(r'Secret Key: (\w+)', user_data).group(1)

                if secret_key == stored_secret_key:
                    if new_password == confirm_password:
                        user_data = re.sub(r'Password: (\w+)', f'Password: {new_password}', user_data)
                        with open(file_path, "w", encoding="utf-8") as updated_file:
                            updated_file.write(user_data)
                        return JSONResponse(content={"message": "Password reset successful"})
                    else:
                        return JSONResponse(content={"message": "Passwords do not match"}, status_code=400)
                else:
                    return JSONResponse(content={"message": "Invalid secret key"}, status_code=400)

        return JSONResponse(content={"message": "Invalid credentials for password reset"}, status_code=400)
    else:
        return JSONResponse(content={"message": "Invalid input"}, status_code=400)

@app.get("/get_secret_key")
async def get_secret_key(username: str):
    if username:
        file_path = os.path.join(data_directory, f"{username}.txt")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as user_file:
                user_data = user_file.read()
                stored_secret_key = re.search(r'Secret Key: (\w+)', user_data).group(1)
                return JSONResponse(content={"secretKey": stored_secret_key})

    return JSONResponse(content={"secretKey": None})

    # Updated provide_feedback route


@app.post("/provide_feedback")
async def provide_feedback(request: Request):
    form_data = await request.form()
    bot_response = form_data.get('bot_response')
    feedback = form_data.get('feedback')
    if not feedback:
        return PlainTextResponse("Please provide feedback for the bot's response.", status_code=400)

    # Save feedback to a text file
    with open(feedback_file_path, "a", encoding="utf-8") as feedback_file:
        feedback_file.write(f"User Message: {um}\n")
        feedback_file.write(f"Bot Response: {bot_response}\n")
        feedback_file.write(f"Feedback: {feedback}\n\n")

    return PlainTextResponse("Feedback received successfully.")

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
