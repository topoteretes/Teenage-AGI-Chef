import openai
import os
import pinecone
import yaml
import time
from dotenv import load_dotenv
import nltk
from langchain.text_splitter import NLTKTextSplitter
from typing import Optional
# Download NLTK for Reading
nltk.download('punkt')
import subprocess
import datetime
# Initialize Text Splitter
text_splitter = NLTKTextSplitter(chunk_size=2500)
from gptrim import trim

# Load default environment variables (.env)
load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL") or "gpt-3.5-turbo"

OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", 0.0))
def openai_call(
    prompt: str,
    model: str = OPENAI_MODEL,
    temperature: float = OPENAI_TEMPERATURE,
    max_tokens: int = 2000,
):
    while True:
        try:
            if model.startswith("llama"):
                # Spawn a subprocess to run llama.cpp
                cmd = ["llama/main", "-p", prompt]
                result = subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True)
                return result.stdout.strip()
            else:
                # Use chat completion API
                messages=[
                    {"role": "system", "content": "You are an intelligent agent with thoughts and memories. You have a memory which stores your past thoughts and actions and also how other users have interacted with you."},
                    {"role": "system", "content": "Keep your thoughts relatively simple and concise"},
                    {"role": "user", "content": prompt},
                    ]
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    n=1,
                    stop=None,
                )
                return response.choices[0].message.content
        except openai.error.RateLimitError:
            print(
                "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
            )
            time.sleep(10)  # Wait 10 seconds and try again
        else:
            break

# def generate(prompt):
#     completion = openai.ChatCompletion.create(
#     model=OPENAI_MODEL,
#     messages=[
#         {"role": "system", "content": "You are an intelligent agent with thoughts and memories. You have a memory which stores your past thoughts and actions and also how other users have interacted with you."},
#         {"role": "system", "content": "Keep your thoughts relatively simple and concise"},
#         {"role": "user", "content": prompt},
#         ]
#     )
#
#     return completion.choices[0].message["content"]

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_ENV = os.getenv("PINECONE_API_ENV")
#PINECONE_API_ENV = "asia-southeast1-gcp"
    
# Prompt Initialization
with open('prompts.yaml', 'r') as f:
    data = yaml.load(f, Loader=yaml.FullLoader)

# internalThoughtPrompt = data['internal_thought']
# externalThoughtPrompt = data['external_thought']
# internalMemoryPrompt = data['internal_thought_memory']
# externalMemoryPrompt = data['external_thought_memory']

# Thought types, used in Pinecone Namespace
THOUGHTS = "Thoughts"
QUERIES = "Queries"
INFORMATION = "Information"
ACTIONS = "Actions"

# Top matches length
k_n = 3

# initialize pinecone
pinecone.init(api_key=PINECONE_API_KEY, environment=PINECONE_API_ENV)

# initialize openAI
openai.api_key = OPENAI_API_KEY # you can just copy and paste your key here if you want

def get_ada_embedding(text):
        text = text.replace("\n", " ")
        return openai.Embedding.create(input=[text], model="text-embedding-ada-002")[
            "data"
        ][0]["embedding"]


class Agento():
    def __init__(self, table_name=None, user_id: Optional[str] = "123", session_id: Optional[str] = None) -> None:
        self.table_name = table_name
        self.user_id = user_id
        self.session_id = session_id
        self.memory = None
        self.thought_id_timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]  # Timestamp with millisecond precision
        self.last_message = ""

    def set_user_session(self, user_id: str, session_id: str) -> None:
        self.user_id = user_id
        self.session_id = session_id

    def createIndex(self, table_name=None):
        # Create Pinecone index
        if(table_name):
            self.table_name = table_name

        if(self.table_name == None):
            return

        dimension = 1536
        metric = "euclidean"
        pod_type = "p1"
        if self.table_name not in pinecone.list_indexes():
            pinecone.create_index(
                self.table_name, dimension=dimension, metric=metric, pod_type=pod_type
            )

        # Give memory
        #my-agent
        #        self.memory = pinecone.Index(self.table_name)
        self.memory = pinecone.Index(self.table_name)

    
    # Adds new Memory to agent, types are: THOUGHTS, ACTIONS, QUERIES, INFORMATION
    def updateMemory(self, new_thought, thought_type):


        if thought_type==INFORMATION:
            new_thought = "This is information fed to you by the user:\n" + new_thought
        elif thought_type==QUERIES:
            new_thought = "The user has said to you before:\n" + new_thought
        elif thought_type==THOUGHTS:
            # Not needed since already in prompts.yaml
            # new_thought = "You have previously thought:\n" + new_thought
            pass
        elif thought_type==ACTIONS:
            # Not needed since already in prompts.yaml as external thought memory
            pass

        vector = get_ada_embedding(new_thought)
        upsert_response = self.memory.upsert(
        vectors=[
            {
            'id':f"thought-{self.thought_id_timestamp}",
            'values':vector, 
            'metadata':
                {"thought_string": new_thought, "user_id": self.user_id
                }
            }],
	    namespace=thought_type,
        )



    # Agent thinks about given query based on top k related memories. Internal thought is passed to external thought
    # def internalThought(self, query) -> str:
    #     # query_embedding = get_ada_embedding(query)
    #     # query_results = self.memory.query(query_embedding, top_k=1, include_metadata=True, namespace=QUERIES, filter={'user_id': {'$eq': self.user_id}})
    #     # thought_results = self.memory.query(query_embedding, top_k=1, include_metadata=True, namespace=THOUGHTS, filter={'user_id': {'$eq': self.user_id}})
    #     # results = query_results.matches + thought_results.matches
    #     # sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
    #     # top_matches = "\n\n".join([(str(item.metadata["thought_string"])) for item in sorted_results])
    #     # #print(top_matches)
    #     #
    #     internalThoughtPrompt = data['internal_thought']
    #     internalThoughtPrompt = internalThoughtPrompt.replace("{query}", query)
    #     #     .replace("{top_matches}", top_matches).replace("{last_message}", self.last_message)
    #     print("------------INTERNAL THOUGHT PROMPT------------")
    #     print(internalThoughtPrompt)
    #     internalThoughtPrompt = trim(internalThoughtPrompt)
    #     internal_thought = openai_call(internalThoughtPrompt) # OPENAI CALL: top_matches and query text is used here
    #
    #     # Debugging purposes
    #     #print(internal_thought)
    #
    #     internalMemoryPrompt = data['internal_thought_memory']
    #     internalMemoryPrompt = internalMemoryPrompt.replace("{query}", query).replace("{internal_thought}", internal_thought).replace("{last_message}", self.last_message)
    #     self.updateMemory(internalMemoryPrompt, THOUGHTS)
    #     return internal_thought, top_matches

    def action(self, query) -> str:
        # internal_thought, top_matches = self.internalThought(query)
        
        externalThoughtPrompt = data['external_thought']

        externalThoughtPrompt = externalThoughtPrompt.replace("{query}", query)
            #.replace("{top_matches}", top_matches).replace("{internal_thought}", internal_thought).replace("{last_message}", self.last_message)
        print("------------EXTERNAL THOUGHT PROMPT------------")
        print(externalThoughtPrompt)
        # externalThoughtPrompt = trim(externalThoughtPrompt)
        external_thought = openai_call(externalThoughtPrompt) # OPENAI CALL: top_matches and query text is used here

        # externalMemoryPrompt = data['external_thought_memory']
        # externalMemoryPrompt = externalMemoryPrompt.replace("{query}", query).replace("{external_thought}", external_thought)
        # self.updateMemory(externalMemoryPrompt, THOUGHTS)
        # request_memory = data["request_memory"]
        # self.updateMemory(request_memory.replace("{query}", query), QUERIES)
        # self.last_message = query
        return external_thought

    # Make agent think some information
    def think(self, text) -> str:
        self.updateMemory(text, THOUGHTS)


    # Make agent read some information
    def read(self, text) -> str:
        texts = text_splitter.split_text(text)
        vectors = []
        for t in texts:
            t = "This is information fed to you by the user:\n" + t
            vector = get_ada_embedding(t)
            vectors.append({
                'id':f"thought-{self.thought_id_timestamp}",
                'values':vector, 
                'metadata':
                    {"thought_string": t, "user_id": self.user_id
                     }
                })


        upsert_response = self.memory.upsert(
        vectors,
	    namespace=INFORMATION,
        )





   
