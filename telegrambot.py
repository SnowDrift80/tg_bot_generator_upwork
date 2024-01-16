import asyncio
import sys
import importlib
from openai import OpenAI, NotFoundError, OpenAIError
from config import BOT_CONSTANTS as BC
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton # new
from telegram.ext import (
    filters,
    MessageHandler,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackContext,
) 

from utils import SharedUtils
from document_driver_base import DocumentDriverBase
import logging



# Initialize OpenAI client
OPENAI_CLIENT = OpenAI(api_key=BC.OPENAI_API_KEY)
# dynamic attribute method lookup for logging level based on config.py entry
log_level = getattr(logging, BC.LOGGING_LEVEL.upper(), None)
logging.basicConfig(level=log_level if BC.VERBOSE else logging.INFO)


class TelegramThread:
    def __init__(self, tg_thread_id, document_name, document_object):
        self.tg_thread_id = tg_thread_id
        self.document_name = document_name
        self.document_object = document_object
  

class TelegramBot:
    def __init__(self):
        self.oai_tg_id_mapper = {}
        self.bot_msg_id_list = []
        self.user_state = {}
        self.tg_thread_to_document_mapper = {}
        
        try:
            self.openai = OPENAI_CLIENT
            self.assistant = OPENAI_CLIENT.beta.assistants.retrieve(BC.OPENAI_ASSISTANT_ID)
        except NotFoundError as e:
            print(f"Assistant not found error? {e}")
            print(f"bot server terminated - the assistant id is probably wrong")
            sys.exit()
            
        self.application = ApplicationBuilder().token(BC.TG_BOT_TOKEN).build()
        
        create_handler = CommandHandler(
            'create', self.create_async
            )
        
        echo_handler = MessageHandler(
            filters.TEXT & (~filters.COMMAND), 
            lambda update, context: self.echo_async(update, context),
            )
        
        for document_type in BC.DOCUMENT_TYPES:
            document_name = document_type['display_name']
            document_class_path = document_type['class_path']
            
            handler = MessageHandler(
                filters.Regex(fr'^{document_name}$'),
                lambda update, context, doc_name=document_name: self.handle_instructions(update, context, doc_name)
                )
    
            self.application.add_handler(handler)  

        
        self.application.add_handler(create_handler)
        self.application.add_handler(echo_handler)

    # asynchronous function wrapper for create() method (command: /create)    
    async def create_async(self, update: Update, context: CallbackContext):
        if len(self.tg_thread_to_document_mapper) > 0:
            threads_to_delete = []
            for thread_id, thread in self.tg_thread_to_document_mapper.items():
                if thread.document_object.is_complete():
                    threads_to_delete.append(thread_id)
            for thread_id in threads_to_delete:
                logging.debug(f"create_async: removed an inactive task #{thread_id} from dictionary")
                del self.tg_thread_to_document_mapper[thread_id]
        # we want to check if we have reached the maximum of allowed concurrent tasks
        # if BC.CONCURRENCY is 0, then there is no limit to the number of concurrent tasks
        if BC.CONCURRENCY >= 1:
            if len(self.tg_thread_to_document_mapper) >= BC.CONCURRENCY:
                logging.debug("Too many tasks - wait until running tasks finish.")
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"<b>Max allowed tasks is {BC.CONCURRENCY}.</b>\nCurrently {len(self.tg_thread_to_document_mapper)} task(s) active.\n\nRequest rejected.",
                    parse_mode='html'
                )
                return
        asyncio.create_task(self.create(update, context))


    # asynchronous function wrapper for echo() method
    # The echo function is the default function to process user messages (chat)
    async def echo_async(self, update: Update, context: CallbackContext):
        asyncio.create_task(self.echo(update, context))

    # instructions handler
    # user decided to enter instructions. user_status flag is set to 'instructions'
    # next user input will be handled by the echo function
    async def handle_instructions(self, update: Update, context: CallbackContext, document_name):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Please enter your instructions:"
        )
        self.set_user_status(update.effective_chat.id, document_name)

    
        
    # Telegram create document menu
    # allows user to chose type of document to be created
    async def create(self, update: Update, context: CallbackContext) -> None:
        tg_thread_id = update.effective_chat.id
        document_types = BC.DOCUMENT_TYPES
        
        #Convert document types from config.py to a list o lists for ReplyKeyboardMarkup
        keyboard_options = [[doc['display_name']] for doc in document_types]
        keyboard_options.append(['cancel']) # adding 'cancel' as menu option
        self.set_user_status(user_id=tg_thread_id, state="busy")
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text = "What type of document would you like to create?",
            reply_markup=ReplyKeyboardMarkup(keyboard_options, one_time_keyboard=True),
            parse_mode='html'
        )
        
        
    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg_thread_id = update.effective_chat.id
        if tg_thread_id in self.tg_thread_to_document_mapper:
            if self.tg_thread_to_document_mapper[tg_thread_id].document_object.is_complete():
                self.set_user_status(tg_thread_id, "chat")
                del self.tg_thread_to_document_mapper[tg_thread_id]
                
            
        logging.debug(f'tg_thread_id: {tg_thread_id}')
        
        # we don't the user to interfere during document creation
        # but allow him to send a cancel command just by writing 'cancel'
        try:
            message_text = update.message.text
        except AttributeError as e:
            print("update.message.text is not existing")
            message_text = ""
            
        user_status = self.get_user_status(tg_thread_id)
        if user_status == "busy":
            if update.message:
                message_text = update.message.text
                if message_text =='cancel' and tg_thread_id not in self.tg_thread_to_document_mapper:
                    self.set_user_status(tg_thread_id, "chat")
                    return
            self.set_user_status(tg_thread_id, "chat")
            

        # Iterate through all document types defined in config.py 
        # and check if users status equals to any known document 
        # type name as defined in DOCUMENT_TYPES.display_name.
        #
        # The required module is dynamically imported using importlib.
        # Finally a fully implemented document driver class based on 
        # the DocumentDriverBase interface class is instantiated 
        # and its fully implemented execute method is called to start 
        # the process of the document generation.
        #
        # The every document object is stored in the tg_thrad_to_document_mapper dictionary.
        # All its methods and public attributes must be accessed through the dictionary.
        # This is for thread safety.
        #
        # This solution allows to implement and add new document_drivers
        # like a plug-in.
        for document_type in BC.DOCUMENT_TYPES:
            if self.get_user_status(tg_thread_id) == document_type['display_name']:
                self.set_user_status(tg_thread_id, "busy")
                logging.debug(f"Process to generate new document of type {user_status} was triggered.")
                module_name, class_name = document_type['class_path'].rsplit('.', 1)
                module = importlib.import_module(module_name)
                document_driver_class = getattr(module, class_name)
                new_document = document_driver_class()
                this_document_task = TelegramThread(tg_thread_id=tg_thread_id, document_name=document_type['display_name'], document_object=new_document) # create an ordinary list
                self.tg_thread_to_document_mapper[this_document_task.tg_thread_id] = this_document_task # add above list as value under the tg_thread_id key
                # await self.tg_thread_to_document_mapper[tg_thread_id].document_object.execute(update, context, message_text)
                asyncio.create_task(self.tg_thread_to_document_mapper[tg_thread_id].document_object.execute(update, context, message_text))
                return
            
        if tg_thread_id in self.tg_thread_to_document_mapper:
            # await self.tg_thread_to_document_mapper[tg_thread_id].document_object.execute(update, context, message_text)
            asyncio.create_task(self.tg_thread_to_document_mapper[tg_thread_id].document_object.execute(update, context, message_text))
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
            logging.debug("Editing of message not yet supported")
            return
        
        chat = await context.bot.get_chat(tg_thread_id) # get the chat
        chat_type = chat.type
        
        chat_title = chat.title if chat.title else "Private Chat"
        
        if not update.message.reply_to_message:
        
            if chat_type == 'private':
                logging.debug(f"Received a message in a private chat with user ID: {tg_thread_id}")
            elif chat_type in ['group', 'supergroup']:
                logging.debug(f"Received a message in a group '{chat_title}' with ID: {tg_thread_id}")
            elif chat_type == 'channel':
                logging.debug(f"Received a message in a channel '{chat_title}' with ID: {tg_thread_id}")
            else:
                logging.debug(f"Receive a message in an unknown chat type with ID: {tg_thread_id}")

                
            if chat_type in ['group', 'supergroup', 'channel'] and not any(call_sign.lower() in tg_message_text.lower() for call_sign in BC.TG_BOT_CALLSIGNS):
                logging.debug('message not addressed to the bot')
                return
            
        elif not self.is_bot_msg(update.message.reply_to_message.id):
            logging.debug('reply to message is not addressed at bot')
            return
            
        try:
            oai_thread_id = self.get_thread(tg_thread_id=tg_thread_id)

            # existing chat thread or a new one (existing chat or new chat, create or get ids in mapper)
            if oai_thread_id is None:
                oai_thread = OPENAI_CLIENT.beta.threads.create()
                oai_thread_id = oai_thread.id
                logging.debug(f"tg_thread_id = {tg_thread_id}")
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
                logging.debug(run.status)
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
                
        except (AttributeError, OpenAIError, IndexError, TypeError, asyncio.CancelledError, Exception) as e:
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
            logging.debug(f"add_thread: tg_thread_id = {tg_thread_id}")
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
