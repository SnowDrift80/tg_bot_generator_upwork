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
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text = "Choose an option:",
            reply_markup=ReplyKeyboardMarkup([['enter instructions', 'cancel']], one_time_keyboard=True),
            parse_mode='html'
        )
        
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
        chapter_titles = {}
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
            
            oai_docgen_thread = OPENAI_CLIENT.beta.threads.create()
            oai_docgen_thread_id = oai_docgen_thread.id
            
            # set language - ideally this would be either set by the Telegram user
            # and/or by using the telegram application to check his locale setting.
            language = await self.identify_language(instruction_text)

            # Create Parent-Chapters
            prompt = f"""
                Your Role: Functioning as a generative artificial intelligence, your expertise lies in crafting the scaffold or structure of a lecture.
                Knowledge: Your task involves utilizing your general knowledge, intentionally without any attached documents. Please refrain from expressing dissatisfaction with this arrangement.
                Your Task: Generate a lecture structure with chapter titles based on the User-Input provided.
                Response Content: Your response must consist of minimum 1 chapter and never exceed 3 chapters. Enumerate each chapter incrementally starting from 1, with a line-feed character at the end of each line. Do not comment. Do never address the user. Do not write an introduction. Limit your answer to the chapter-titles only.
                Language: Generate your response in the {language} language.
                Social Responsibility: Avoid suggesting politically controversial chapters or those infringing on individual privacy, unless the subject is of public interest, and the suggested chapter or sub-chapter is already part of the public domain.
                The Purpose of This Task: The scaffold, or list of chapters, generated by you will serve as the foundation for iteratively generating sub-chapters in a subsequent process.
                Create the structure based on the following user-input: {instruction_text}
            """
            print(f"\n\nprompt:\n{prompt}\n\n") if BC.VERBOSE else None
            # create prompt
            message = OPENAI_CLIENT.beta.threads.messages.create(
                thread_id=oai_docgen_thread_id,
                role="user",
                content=prompt
            )
            
            # run prompt
            run = OPENAI_CLIENT.beta.threads.runs.create(
            thread_id=oai_docgen_thread_id,
            assistant_id=self.assistant.id,
            instructions=BC.OPENAI_INSTRUCTIONS
            )
            
            # wait async for response for OpenAI and check status every 5 seconds
            while True:
                await context.bot.send_chat_action(chat_id=tg_thread_id, action='typing')
                run = OPENAI_CLIENT.beta.threads.runs.retrieve(
                    thread_id = oai_docgen_thread_id,
                    run_id = run.id
                )
                print(run.status) if BC.VERBOSE else None
                if run.status == "completed":
                    break
                await asyncio.sleep(5)
                
            # once "completed", get messages (response from OpenAI)
            messages = OPENAI_CLIENT.beta.threads.messages.list(
                thread_id=oai_docgen_thread_id
            )
            print(f"structure message: {messages}") if BC.VERBOSE else None

            # pick clean response
            last_message = messages.data[0]
            oai_response = last_message.content[0].text.value
            oai_response = self.remove_reference(oai_response=oai_response)
            
            print(f"\n\nscaffolding main structure... \n\n {oai_response}\n\n\n") if BC.VERBOSE else None
            
            # update telegram with the main chapters:
            tg_main_chapters = "scaffolding main structure... \n\n" + oai_response
            await context.bot.send_message(chat_id=tg_thread_id, text=tg_main_chapters)

            
            # Split the text into a list of sub-strings
            text = oai_response.split('\n')
        except Exception as e:
            print(f"Error while scaffolding main chapters: {e}\nExit to chat mode.\n")
            self.set_user_status(user_id=tg_thread_id, state="chat")
            
            
        all_main_chapters = '\n'.join(line for line in text)
        
        try:
            # iterate through lines and create sub-chapters.
            for line in text:
                tg_message = f"scuffolding sub structure for '{line}'"
                await context.bot.send_message(chat_id=tg_thread_id, text=tg_message)
                if line.strip() == '':
                    continue
                line = line.lstrip()
                print(line) if BC.VERBOSE else None
                
                prompt = f"""
                    Your Role: You function as a generative artificial intelligence, specializing in the creation of academic essays and lectures.
                    Your Task: Generate a minimum of 1 and a maximum of 2 sub-chapter titles for the current parent-chapter title provided ({line}). Refer to the overview of all parent-chapter titles ({all_main_chapters}) for context.
                    Enumeration: Each sub-chapter title is enumerated with a prefix representing the parent-chapter title number, followed by a dot separator, and an incrementally enumerated suffix starting from 1 followe by a space character.
                    Format: The format requires each line to commence with the sub-chapter number, followed by the sub-chapter title text and a line-feed at the end.
                    Knowledge Source: Utilize your general knowledge acquired during training.
                    Language: Present your response in the {language} language.
                    Social Responsibility: When addressing topics within the public domain, such as public figures or organizations, provide a comprehensive response based on accessible data from your training.
                    Style: Tailor your expressions and language style to suit the audience, composed of high-profile scholars and academics.
                    User Instructions: Follow the provided {instruction_text}.            
                """
                message = OPENAI_CLIENT.beta.threads.messages.create(
                    thread_id=oai_docgen_thread_id,
                    role="user",
                    content=prompt
                )
                
                run = OPENAI_CLIENT.beta.threads.runs.create(
                thread_id=oai_docgen_thread_id,
                assistant_id=self.assistant.id,
                instructions=BC.OPENAI_INSTRUCTIONS
                )
                
                while True:
                    await context.bot.send_chat_action(chat_id=tg_thread_id, action='typing')
                    run = OPENAI_CLIENT.beta.threads.runs.retrieve(
                        thread_id = oai_docgen_thread_id,
                        run_id = run.id
                    )
                    print(run.status) if BC.VERBOSE else None
                    if run.status == "completed":
                        break
                    await asyncio.sleep(5)
                
                messages = OPENAI_CLIENT.beta.threads.messages.list(
                    thread_id=oai_docgen_thread_id
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
                # we create a list containing all the sub-chapter-title strings
                chapter_titles[line] = [line.strip() for line in oai_response.splitlines()]
                tg_subchapters = "\n" + oai_response + "\n\n"
                await context.bot.send_message(chat_id=tg_thread_id, text=tg_subchapters)

            # produce string with all chapters sequentually listed for AI reference
            all_chapter_titles = ""
            for parent_chapter, sub_chapter_list in chapter_titles.items():
                all_chapter_titles += parent_chapter.strip() + "\n"
                for sub_chapter in sub_chapter_list:
                    all_chapter_titles += sub_chapter.strip() + "\n"
                
                
            print(f"The complete scaffold: \n {all_chapter_titles}") if BC.VERBOSE else None

        except Exception as e:
            print(f"Error while scaffolding sub-chapters: {e}\nExit to chat mode.\n")
            self.set_user_status(user_id=tg_thread_id, state="chat")

        
        gen_doc = ""
        
        tg_parent_chapter_message = None
        tg_sub_chapter_message = None
        chevron = "   "
        
      
        try:
            for parent_chapter, sub_chapter_list in chapter_titles.items():
                bold_index = 0 # reset bold index for chevron animation because new main chapter
                gen_doc += "\n" + parent_chapter + "\n\n" # add empty line + parent chapter
                if not tg_parent_chapter_message:
                    tg_parent_chapter_message = await context.bot.send_message(chat_id=tg_thread_id, text=f"\n\nprocessing parent-chapter {parent_chapter}\n\n")
                else:
                    await context.bot.edit_message_text(chat_id=tg_thread_id, message_id=tg_parent_chapter_message.message_id, text=f"\n\nprocessing parent-chapter {parent_chapter}\n\n")
                    
                for sub_chapter in sub_chapter_list:
                    bold_index = 0 # reset bold index for chevron animatino because of new sub chapter
                    gen_doc += "\n" + sub_chapter + "\n" # add empty line + parent chapter
                    
                    prompt = f"""
                    Your role: You are a generative artificial intelligence. Your speciality is to generate academic essays and lectures.
                    Your task: You will be given a topic and a chapter title. Your task is to generate the text for the title in context of the title and the topic.
                    Knowledge: You will use your general knowledge that was given to you by your training. If there is a document attached, you will use this knowledge too and if not attached you will use your general knowledge.
                    Comments: You strictly adhere to deliver content only. You never comment your content or lack thereof. You will never mention that you don't know something and you will never apologize.
                    Content: You will create content only for sub-chapters. In case of parent chapters, you will just return the parent chapter title and you will refrain from adding further content.
                    Length: the content you create for sub-chapters should be at minimum 50 characters and a maximum of 100 characters in length.
                    Language: You will generate your response in {language} language.
                    Social responsibility: If the subject in question belongs to the public domain, for example a public figure or organisation, even if the topic may be perceived controversial, you will give a full response based on available data you gained from your training.
                    Style: Your audience is consisting of high-profile scholars and academics, therefore choose expressions and language style accordingly.
                    Purpose: The purpose of this task is to generate the content for the present sub-chapter.
                    Topic in context to each chapter: {instruction_text}
                    List of all chapters and sub-chapters belonging to this document for your reference: {all_chapter_titles}
                    In general context to the topic, generate the content expanding on the following subchapter title, without mentioning the title explicitly in the content you create: \"{sub_chapter}\"
                    """
                    message = OPENAI_CLIENT.beta.threads.messages.create(
                        thread_id=oai_docgen_thread_id,
                        role="user",
                        content=prompt
                    )
                    
                    run = OPENAI_CLIENT.beta.threads.runs.create(
                    thread_id=oai_docgen_thread_id,
                    assistant_id=self.assistant.id,
                    instructions=BC.OPENAI_INSTRUCTIONS
                    )
                    
                    counter = 0
                    while True:
                        counter += 1
                        
                        chevron = self.shift_chevron(counter)
                            
                        # preparing chevron bold index
                        if not tg_sub_chapter_message: 
                            message_text = f"\n\nprocessing sub-chapter {sub_chapter[:25]}...{chevron}\n\n"
                            tg_sub_chapter_message = await context.bot.send_message(chat_id=tg_thread_id, text=message_text, parse_mode='markdown')
                        else:
                            updated_message_text = f"\n\nprocessing sub-chapter {sub_chapter[:25]}...{chevron}\n\n"
                            try:
                                await context.bot.edit_message_text(chat_id=tg_thread_id, message_id=tg_sub_chapter_message.message_id, text=updated_message_text, parse_mode='markdown')
                            except Exception as e:
                                counter += 1
                                chevron = self.shift_chevron(counter)
                                print("Telegram refuses to update a message with the same text.")

                        await context.bot.send_chat_action(chat_id=tg_thread_id, action='typing')
                        run = OPENAI_CLIENT.beta.threads.runs.retrieve(
                            thread_id = oai_docgen_thread_id,
                            run_id = run.id
                        )
                        print(run.status) if BC.VERBOSE else None
                        if run.status == "completed":
                            break
                        await asyncio.sleep(3)
                    
                    messages = OPENAI_CLIENT.beta.threads.messages.list(
                        thread_id=oai_docgen_thread_id
                    )
                    # pick correct message
                    last_message = messages.data[0]
                    oai_response = last_message.content[0].text.value
                    oai_response = self.remove_reference(oai_response=oai_response)
                    print(f"\n\n {sub_chapter}\n") if BC.VERBOSE else None
                    print(f"{oai_response}\n\n") if BC.VERBOSE else None
                    # sometimes the AI generates content including a leading sub-chapter title
                    # we don't want that as we add the sub-chapter title programmatically
                    if oai_response.startswith(line):
                        # Replace the sub-title with an empty string
                        oai_response = oai_response[len(line):]
                    gen_doc += oai_response + "\n" # generated content + empty line

            
            self.create_word_doc("lecture.docx", gen_doc)
            await context.bot.send_document(
                chat_id=tg_thread_id,
                document=open("lecture.docx", 'rb'),
                filename="lecture.docx",
                caption="Here's your Word document!"
            )
            self.set_user_status(user_id=tg_thread_id, state="chat")
            oai_docgen_thread = None  # hand over to garbage collection
            oai_docgen_thread_id = None # hand over to garbage collection
            chapter_titles = {} # reset dicionary and make it ready for the next job

            
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


    def shift_chevron(self, counter):
        chevron = "..."
        if counter == 4:
            counter = 1
        if counter == 1:
            chevron = "*\u00BB*.."
        elif counter == 2:
            chevron = ".*\u00BB*."
        elif counter == 3:
            chevron = "..*\u00BB*"

        return chevron

        
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
        print("Bot is online. Ready.")
        self.application.run_polling()
        
        
if __name__ == '__main__':
    telegram_bot = TelegramBot()
    telegram_bot.run()
            
