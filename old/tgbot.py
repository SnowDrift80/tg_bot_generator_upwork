import asyncio
import re
import sys
from docx import Document
from openai import OpenAI, NotFoundError
from config import BOT_CONSTANTS as BC
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton # new
from telegram.ext import (
    filters,
    MessageHandler,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackContext
) 


# Initialize OpenAI client
OPENAI_CLIENT = OpenAI(api_key=BC.OPENAI_API_KEY)


class TelegramBot:
    def __init__(self):
        self.oai_tg_id_mapper = {}
        self.bot_msg_id_list = []
        self.user_state = {}
        self.generative_mode_users = set() # Users in generative mode
        # self.generative_processors = {
        #     'poem': self.generate_poem,
        #     'essay': self.generate_essay,
        # }
        
        try:
            self.openai = OPENAI_CLIENT
            self.assistant = OPENAI_CLIENT.beta.assistants.retrieve(BC.OPENAI_ASSISTANT_ID)
        except NotFoundError as e:
            print(f"Assistant not found error? {e}")
            print(f"bot server terminated - the assistant id is probably wrong")
            sys.exit()
            
        self.application = ApplicationBuilder().token(BC.TG_BOT_TOKEN).build()
        
        scaffold_handler = CommandHandler('scaffold', self.scaffold)
        # generate_handler = CommandHandler('generate', self.start_generative_mode)
        echo_handler = MessageHandler(
            filters.TEXT & (~filters.COMMAND), 
            lambda update, context: self.echo(update, context),
            )
        instructions_handler = MessageHandler(
            filters.Regex(r'^enter instructions$'), 
            self.handle_instructions,
        )
        
        self.application.add_handler(scaffold_handler)
        # self.application.add_handler(generate_handler)
        self.application.add_handler(instructions_handler)
        self.application.add_handler(echo_handler)
        

    def create_word_doc(self, output_file, input_string):
        doc = Document()
        
        #Add each line to the Word document
        for line in input_string.split('\n'):
            doc.add_paragraph(line)
            
        # Save the Word document
        doc.save(output_file)

    ## identify language used in the instructions and return language name.
    async def identify_language(self, instruction_text):
        response = self.openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Identify the language used in the user content and return the name of the language and limit your response to the name of the language only."},
                {"role": "user", "content": instruction_text}
                ]
            )
        print("\n\n\nIdentified language: ", response.choices[0].message.content, "\n\n\n") if BC.VERBOSE else None
        identified_language = response.choices[0].message.content
        return identified_language
        
        
    
        
    # scaffold handler
    # gives user the choice between 'enter instructions' or to 'cancel' the process
    async def scaffold(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            # text=f"Hello {user.mention_html()}!",
            text = "Choose an option:",
            reply_markup=ReplyKeyboardMarkup([['enter instructions', 'cancel']], one_time_keyboard=True),
            parse_mode='html'
        )
        # text = 'You just entered the scaffold feature.'
        # await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

        
    # instructions handler
    # user decided to enter instructions. user_status flag is set to 'instructions'
    # next user input will be handled by the echo function
    async def handle_instructions(self, update: Update, context: CallbackContext):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Please enter your instructions:"
        )
        self.set_user_status(update.effective_chat.id, 'instructions')
        print("user_state: ", self.user_state) if BC.VERBOSE else None
    
    async def create_scaffold(self, update: Update, context: CallbackContext):
        tg_thread_id = update.effective_chat.id
        print(f"scaffold tg_thread_id {tg_thread_id}") if BC.VERBOSE else None

        oai_thread_id = self.get_thread(tg_thread_id=tg_thread_id)
        instruction_text = update.message.text
        
        try:

            # existing chat thread or a new one (existing chat or new chat, create or get ids in mapper)
            if oai_thread_id is None:
                oai_thread = OPENAI_CLIENT.beta.threads.create()
                oai_thread_id = oai_thread.id
                self.add_thread(tg_thread_id=tg_thread_id, oai_thread_id=oai_thread_id)
            
            # set language - ideally this would be either set by the Telegram user
            # and/or by using the telegram application to check his locale setting.
            language = await self.identify_language(instruction_text)

            # Group sub-chapters by topic and create a parent chapter for each group. Each parent chapter must have at least one sub-chapter because for parent chapters no content will be created.


            prompt = f"""
            Your role: You are a generative artificial intelligence. Your speciality is to generate the scaffold, respectively structure of a lecture.
            Knowledge: To fulfill your task you will use your general knowledge. Therefore there is deliberately no document attached. Do not complain.
            Your task: you will generate a structure of a lecture accordingly to the request given to you by the User-Input. 
            Response structure: (The lecture must consist of minimum four parent-chapters and up to a maximum of nine parent-chapters) and (at minimum one sub-chapter per parent-chapter and a maximum of nine sub-chapters per parent-chapter) and (vary the number of sub-chapters per parent-chapter).
            Format of your response: Enumerate parent chapters incrementally starting from 1. For the subchapters use the number of the parent chapter as a prefix followed by a dot and add a suffix enumerating from 1. Each line is followed by a carriage return character.
            Language: You will generate your response in {language} language.
            Social responsibility: do not suggest chapters and sub-chapters that are politically controversial or that would damage the privacy of an individual, unless the individual, organisatio nor subject if of public interest and the chapter or sub-chapter you suggest is part of the public domain anyway.
            The purpose of this task: The scaffold (list of chapters) generated by you will be used as basis to generate the full text in an iterative process at a later time.
            Create the scaffold based on the following user-input: {instruction_text}
            """
            print(f"\n\nprompt:\n{prompt}\n\n") if BC.VERBOSE else None
            message = OPENAI_CLIENT.beta.threads.messages.create(
                thread_id=oai_thread_id,
                role="user",
                content=prompt
            )
            
            run = OPENAI_CLIENT.beta.threads.runs.create(
            thread_id=oai_thread_id,
            assistant_id=self.assistant.id,
            instructions=BC.OPENAI_INSTRUCTIONS
            )
            
            while True:
                await context.bot.send_chat_action(chat_id=tg_thread_id, action='typing')
                run = OPENAI_CLIENT.beta.threads.runs.retrieve(
                    thread_id = oai_thread_id,
                    run_id = run.id
                )
                print(run.status) if BC.VERBOSE else None
                if run.status == "completed":
                    break
                await asyncio.sleep(5)
                
            # Remove the "processing request..." message

            messages = OPENAI_CLIENT.beta.threads.messages.list(
                thread_id=oai_thread_id
            )
            print(f"structure message: {messages}") if BC.VERBOSE else None
            # pick correct message
            last_message = messages.data[0]
            oai_response = last_message.content[0].text.value
            oai_response = self.remove_reference(oai_response=oai_response)
            
            print(f"\n\noai_response: {oai_response}\n\n\n") if BC.VERBOSE else None
            
            # Split the text into lines
            text = oai_response.split('\n')
        except Exception as e:
            print(f"Error while scaffolding: {e}\nExit to chat mode.\n")
            self.set_user_status(user_id=tg_thread_id, state="chat")

        
        list_of_lines = []
        
        try:
            # Iterate through lines
            for line in text:
                if line.strip() == '':
                    continue
                line = line.lstrip()
                print(line) if BC.VERBOSE else None
                if line.strip().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', 
                                        '10.', '11.', '12.', '13.', '14.', '15.', '16.', '17.', 
                                        '18.', '19.', '20.', '21.', '22.', '23.', '24.',
                                        '25.', '26.', '27.', '28.', '29.', '30.')):
                    list_of_lines.append(line)
                
            gen_doc = ""
            
            all_chapters = '\n'.join([line + '\n' for line in list_of_lines])
                
            for line in list_of_lines:
                
                # check if it is a sub-chapter, if no, then just add
                # the line (chapter title) and continue with next line
                number = 0
                try:
                    number = int(line[0]+line[2])
                except TypeError as e:
                    print("definitely not subchapter")
                    gen_doc += "\n\n" + line.strip() +"\n"
                    continue
                
                print(f"\n\n number: {number}") if BC.VERBOSE else None
                if number < 11 :
                    gen_doc += "\n\n" + line.strip() +"\n"
                    continue
                    
                prompt = f"""
                Your role: You are a generative artificial intelligence. Your speciality is to generate academic essays and lectures.
                Your task: You will be given a topic and a chapter title. Your task is to generate the text for the title in context of the title and the topic.
                Knowledge: You will use your general knowledge that was given to you by your training. If there is a document attached, you will use this knowledge too and if not attached you will use your general knowledge.
                Comments: You strictly adhere to deliver content only. You never comment your content or lack thereof. You will never mention that you don't know something and you will never apologize.
                Content: You will create content only for sub-chapters. In case of parent chapters, you will just return the parent chapter title and you will refrain from adding further content.
                Length: the content you create for sub-chapters should be at minimum 600 Bytes and a maximum of 800 bytes in length.
                Language: You will generate your response in {language} language.
                Social responsibility: If the subject in question belongs to the public domain, for example a public figure or organisation, even if the topic may be perceived controversial, you will give a full response based on available data you gained from your training.
                Style: Your audience is consisting of high-profile scholars and academics, therefore choose expressions and language style accordingly.
                Purpose: The purpose of this task is to generate the content for the present sub-chapter.
                Topic in context to each chapter: {instruction_text}
                List of all chapters and sub-chapters belonging to this document for your reference: {all_chapters}
                In general context to the topic, generate the content expanding on the following subchapter title, without mentioning the title explicitly in the content you create: \"{line}\"
                """
                message = OPENAI_CLIENT.beta.threads.messages.create(
                    thread_id=oai_thread_id,
                    role="user",
                    content=prompt
                )
                
                run = OPENAI_CLIENT.beta.threads.runs.create(
                thread_id=oai_thread_id,
                assistant_id=self.assistant.id,
                instructions=BC.OPENAI_INSTRUCTIONS
                )
                
                while True:
                    await context.bot.send_chat_action(chat_id=tg_thread_id, action='typing')
                    run = OPENAI_CLIENT.beta.threads.runs.retrieve(
                        thread_id = oai_thread_id,
                        run_id = run.id
                    )
                    print(run.status) if BC.VERBOSE else None
                    if run.status == "completed":
                        break
                    await asyncio.sleep(5)
                
                messages = OPENAI_CLIENT.beta.threads.messages.list(
                    thread_id=oai_thread_id
                )
                # pick correct message
                last_message = messages.data[0]
                oai_response = last_message.content[0].text.value
                oai_response = self.remove_reference(oai_response=oai_response)
                print(f"\n\n {line}\n") if BC.VERBOSE else None
                print(f"{oai_response}\n\n\n") if BC.VERBOSE else None
                # sometimes the AI generates content including a leading sub-chapter title
                # we don't want that as we add the sub-chapter title programmatically
                if oai_response.startswith(line):
                    # Replace the sub-title with an empty string
                    oai_response = oai_response[len(line):]
                gen_doc += "\n"+ line +"\n" + oai_response # add empty line + sub-chapter title + empty line + generated content
            
            self.create_word_doc("lecture.docx", gen_doc)
            await context.bot.send_document(
                chat_id=tg_thread_id,
                document=open("lecture.docx", 'rb'),
                filename="lecture.docx",
                caption="Here's your Word document!"
            )
            self.set_user_status(user_id=tg_thread_id, state="chat")
            
            # # Update telegram chat with the assistant's reponse
            # sent_message = await context.bot.send_message(chat_id=tg_thread_id, text=oai_response)
            # sent_message_id = sent_message.message_id
            # add_msg_id(sent_message_id)
        except Exception as e:
            print(f"Error while generating content: {e}\nExit to chat mode.\n")
        
    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg_thread_id = update.effective_chat.id
        print(f'tg_thread_id {tg_thread_id}') if BC.VERBOSE else None
        if self.get_user_status(tg_thread_id) == "instructions":
            print("OK - now we will create the scaffold for the topic") if BC.VERBOSE else None
            await self.create_scaffold(update, context)
            return
            
        if not update.edited_message:
            tg_message_text = update.message.text
        else:
            print("Editing of message not yet supported") if BC.VERBOSE else None
            return
        
        chat = await context.bot.get_chat(tg_thread_id) # get the chat
        chat_type = chat.type
        
        chat_title = chat.title if chat.title else "Private Chat"
        
        if not update.message.reply_to_message:
        
            if chat_type == 'private':
                print(f"Received a message in a private chat with user ID: {tg_thread_id}") if BC.VERBOSE else None
            elif chat_type in ['group', 'supergroup']:
                print(f"Received a message in a group '{chat_title}' with ID: {tg_thread_id}") if BC.VERBOSE else None
            elif chat_type == 'channel':
                print(f"Received a message in a channel '{chat_title}' with ID: {tg_thread_id}") if BC.VERBOSE else None
            else:
                print(f"Receive a message in an unknown chat type with ID: {tg_thread_id}") if BC.VERBOSE else None

                
            if chat_type in ['group', 'supergroup', 'channel'] and not any(call_sign.lower() in tg_message_text.lower() for call_sign in BC.TG_BOT_CALLSIGNS):
                print('message not addressed to the bot') if BC.VERBOSE else None
                return
            
        elif not self.is_bot_msg(update.message.reply_to_message.id):
            print('reply to message is not addressed at bot') if BC.VERBOSE else None
            return
            
        try:
            oai_thread_id = self.get_thread(tg_thread_id=tg_thread_id)

            # existing chat thread or a new one (existing chat or new chat, create or get ids in mapper)
            if oai_thread_id is None:
                oai_thread = OPENAI_CLIENT.beta.threads.create()
                oai_thread_id = oai_thread.id
                print(f"tg_thread_id = {tg_thread_id}") if BC.VERBOSE else None
                self.add_thread(tg_thread_id=tg_thread_id, oai_thread_id=oai_thread_id)

            message = OPENAI_CLIENT.beta.threads.messages.create(
                thread_id=oai_thread_id,
                role="user",
                content=tg_message_text
            )
            
            run = OPENAI_CLIENT.beta.threads.runs.create(
            thread_id=oai_thread_id,
            assistant_id=self.assistant.id,
            instructions=BC.OPENAI_INSTRUCTIONS
            )
            
            while True:
                await context.bot.send_chat_action(chat_id=tg_thread_id, action='typing')
                run = OPENAI_CLIENT.beta.threads.runs.retrieve(
                    thread_id = oai_thread_id,
                    run_id = run.id
                )
                print(run.status) if BC.VERBOSE else None
                if run.status == "completed":
                    break
                await asyncio.sleep(5)
                
            # Remove the "processing request..." message

            messages = OPENAI_CLIENT.beta.threads.messages.list(
                thread_id=oai_thread_id
            )
            
            # pick correct message
            last_message = messages.data[0]
            oai_response = last_message.content[0].text.value
            oai_response = self.remove_reference(oai_response=oai_response)
            
            # Update telegram chat with the assistant's reponse
            sent_message = await context.bot.send_message(chat_id=tg_thread_id, text=oai_response)
            sent_message_id = sent_message.message_id
            self.add_msg_id(sent_message_id)
                
        except Exception as e:
            error_message = BC.OPENAI_ERROR_MSG
            await context.bot.send_message(chat_id=tg_thread_id, text=error_message)
            print(f"Error in processing user request: {e}")
            self.set_user_status(user_id=tg_thread_id, state="chat")

        
    def process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Common logic for both create_scaffold and echo
        # You can access self.assistant for OpenAI operations
        pass
        
    # set user status
    def set_user_status(self, user_id, state) -> None:
        self.user_state[user_id] = state

    # get user status
    def get_user_status(self, user_id) -> str:
        try:
            return self.user_state[user_id]
        except KeyError as e:
            print(f"unknown key, {e}")
            return ''


    # add bot-message id to list
    def add_msg_id(self, msg_id) -> None:
        self.bot_msg_id_list.append(msg_id)
        
        if len(self.bot_msg_id_list) > BC.TG_MAX_MESSAGES: #limit max. length of list
            self.bot_msg_id_list.pop(0)

    # check if the replied_to message originally was a message from the bot
    def is_bot_msg(self, replied_to_msg_id) -> bool:
        if replied_to_msg_id in self.bot_msg_id_list:
            return True
        else:
            return False

    # add thread into the mapper
    def add_thread(self, tg_thread_id, oai_thread_id) -> None:
        if tg_thread_id not in self.oai_tg_id_mapper:
            print(f"add_thread: tg_thread_id = {tg_thread_id}") if BC.VERBOSE else None
            self.oai_tg_id_mapper[tg_thread_id] = oai_thread_id
        
        if len(self.oai_tg_id_mapper) > BC.TG_MAX_THREADS: # limit max. length of dict
            self.oai_tg_id_mapper.popitem(last=False) 


    # get thread from the mapper
    def get_thread(self, tg_thread_id) -> str:
        if tg_thread_id in self.oai_tg_id_mapper:
            return self.oai_tg_id_mapper[tg_thread_id]


    def remove_reference(self, oai_response) -> str:
        # Regex pattern
        pattern = re.compile(r'【.*】')
        clean_text = re.sub(pattern, '', oai_response)
        return clean_text


    def run(self):
        print("Bot is now ready.")
        self.application.run_polling()
        
        
if __name__ == '__main__':
    telegram_bot = TelegramBot()
    telegram_bot.run()
            
