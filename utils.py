import re
from docx import Document
from openai import OpenAI
from config import BOT_CONSTANTS as BC

# Initialize OpenAI client
OPENAI_CLIENT = OpenAI(api_key=BC.OPENAI_API_KEY)


class SharedUtils:
    
    
    ## identify language used in the instructions and return language name.
    @staticmethod # we don't need to instantiate this
    async def identify_language(instruction_text):
        response = OPENAI_CLIENT.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Identify the language used in the user content and return the name of the language and limit your response to the name of the language only."},
                {"role": "user", "content": instruction_text}
                ]
            )
        print("\n\n\nIdentified language: ", response.choices[0].message.content, "\n\n\n") if BC.VERBOSE else None
        identified_language = response.choices[0].message.content
        return identified_language


    @staticmethod # doesn't need to be instantiated
    def remove_reference(oai_response) -> str:
        # Regex pattern
        pattern = re.compile(r'【.*】')
        clean_text = re.sub(pattern, '', oai_response)
        return clean_text


    @staticmethod # I don't see here either why instantiating it
    def shift_chevron(counter):
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
    
    
class DocumentExport():
    
    
    def create_word_doc(self, output_file, input_string):
        doc = Document()
    
        #Add each line to the Word document
        for line in input_string.split('\n'):
            doc.add_paragraph(line)
            
        # Save the Word document
        doc.save(output_file)


        
