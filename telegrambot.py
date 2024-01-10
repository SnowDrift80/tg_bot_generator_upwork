import asyncio
import sys
import importlib
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

from utils import SharedUtils




# Initialize OpenAI client
OPENAI_CLIENT = OpenAI(api_key=BC.OPENAI_API_KEY)
  

class TelegramBot:
    def __init__(self):
        self.oai_tg_id_mapper = {}
        self.bot_msg_id_list = []
        self.user_state = {}
        
        try:
            self.openai = OPENAI_CLIENT
            self.assistant = OPENAI_CLIENT.beta.assistants.retrieve(BC.OPENAI_ASSISTANT_ID)
        except NotFoundError as e:
            print(f"Assistant not found error? {e}")
            print(f"bot server terminated - the assistant id is probably wrong")
            sys.exit()
            
        self.application = ApplicationBuilder().token(BC.TG_BOT_TOKEN).build()
        
        create_handler = CommandHandler(
            'create', self.create
            )
        
        echo_handler = MessageHandler(
            filters.TEXT & (~filters.COMMAND), 
            lambda update, context: self.echo(update, context),
            )
        
        for document_type in BC.DOCUMENT_TYPES:
            document_name = document_type['display_name']
            document_class_path = document_type['class_path']
            document_method = document_type['method']
            
            handler = MessageHandler(
                filters.Regex(fr'^{document_name}$'),
                lambda update, context, doc_name=document_name: self.handle_instructions(update, context, doc_name)
                )
    
            self.application.add_handler(handler)  

        
        self.application.add_handler(create_handler)
        self.application.add_handler(echo_handler)
        

    # instructions handler
    # user decided to enter instructions. user_status flag is set to 'instructions'
    # next user input will be handled by the echo function
    async def handle_instructions(self, update: Update, context: CallbackContext, document_name):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Please enter your instructions:"
        )
        self.set_user_status(update.effective_chat.id, document_name)
        print("user_state: ", self.user_state) if BC.VERBOSE else None

    
        
    # Telegram create document menu
    # allows user to chose type of document to be created
    async def create(self, update: Update, context: CallbackContext) -> None:
        document_types = BC.DOCUMENT_TYPES
        
        #Convert document types to a list o lists for ReplyKeyboardMarkup
        keyboard_options = [[doc['display_name']] for doc in document_types]
        keyboard_options.append(['cancel']) # adding 'cancel' as menu option
        
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text = "What type of document would you like to create?",
            reply_markup=ReplyKeyboardMarkup(keyboard_options, one_time_keyboard=True),
            parse_mode='html'
        )
        
        
    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg_thread_id = update.effective_chat.id
        print(f'tg_thread_id: {tg_thread_id}') if BC.VERBOSE else None
        
        # we don't the user to interfere during document creation
        # but allow him to send a cancel command just by writing 'cancel'
        user_status = self.get_user_status(tg_thread_id)
        if user_status == "busy":
            if update.message:
                message_text = update.message.text
                if message_text =='cancel':
                    self.set_user_status(tg_thread_id, "chat")
                    return
            return

        # iterate through all document types defined in config.py 
        # and check if users status equals to any known document type name.
        # The required module is dynamically imported using importlib
        # Finally the corresponding document driver method is called using getattr.
        # Now it is possible to add additional document drivers just by registering it in config.py!!
        for document_type in BC.DOCUMENT_TYPES:
            if user_status == document_type['display_name']:
                self.set_user_status(tg_thread_id, "busy")
                print(f"Process to generate new document of type {user_status} has been triggered.") if BC.VERBOSE else None
                module_name, class_name = document_type['class_path'].rsplit('.', 1)
                module = importlib.import_module(module_name)
                document_driver_class = getattr(module, class_name)
                new_document = document_driver_class()
                await getattr(new_document, document_type['method'])(update, context)
                self.set_user_status(tg_thread_id, "chat")
                return
     
        # I'm keeping the below commmented code to better understand what happens in the loop above.
        # if self.get_user_status(tg_thread_id) == "Academic Lecture":
        #     print("OK - now we will create the scaffold for the topic") if BC.VERBOSE else None
        #     new_document = LectureDriver()
        #     await new_document.create_lecture(update, context)
        #     return
            
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
            
            # loop until response from OpenAI
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
            oai_response = SharedUtils.remove_reference(oai_response=oai_response)
            
            # Update telegram chat with the assistant's reponse
            sent_message = await context.bot.send_message(chat_id=tg_thread_id, text=oai_response)
            sent_message_id = sent_message.message_id
            self.add_msg_id(sent_message_id)
                
        except Exception as e:
            error_message = BC.OPENAI_ERROR_MSG
            await context.bot.send_message(chat_id=tg_thread_id, text=error_message)
            print(f"Error in processing user request: {e}")
            self.set_user_status(user_id=tg_thread_id, state="chat")


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


    def run(self):
        print("Bot is online. Ready.")
        self.application.run_polling()
