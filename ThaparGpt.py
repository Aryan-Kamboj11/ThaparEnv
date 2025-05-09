import os
import chromadb
from chromadb import EmbeddingFunction
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import ollama  # Changed from huggingface_hub import InferenceClient


class DataLoader:
    def __init__(self):
        self.data_dir = "Structured_Data"
    def load_files(self):
        data = {}
        for filename in os.listdir(self.data_dir):
            if filename.endswith('.txt'):
                with open(os.path.join(self.data_dir,filename),'r') as f:
                    data[filename]=f.read()
        return data
class EmbeddingModel:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
    def embed(self,txt):
        if isinstance(txt, str):
            txt = [txt]
        return self.model.encode(txt)

class VectorDB(DataLoader):
    def __init__(self):
        super().__init__()
        self.client = chromadb.PersistentClient()
        self.embedder = EmbeddingModel()
        self.collections = {}
        for collection_name in ["thapar_hostels", "thapar_academics", "thapar_activities","thapar_placements"]:
            try:
                self.client.delete_collection(collection_name)
            except:
                pass
        self.incollections()   
    def incollections(self):
        
        file_types = {
          "hostels":["Hostel_info.txt"],
          "activities":["TIET_Events.txt","clubs_thapar.txt","Thapar_Societies.txt"],
          "academics":["scholarships.txt","Pg_Course_Fee.txt","Pg_Program_Structure.txt"],
          "placements":["Placement_Record.txt"]  
        }
        
        for col_type,files in file_types.items():
            col_name = f"thapar_{col_type}"
            self.collections[col_type] = self.client.create_collection(name=col_name)
    def chunkData(self,txt,delimiter = "###"):
        return [chunk.strip() for chunk in txt.split(delimiter) if chunk.strip()]
    def  populate_db(self):
        files_data = self.load_files()
        
        for filename,content in files_data.items():
            if 'hostel' in filename.lower():
                col_type ="hostels"
            elif 'scholarship' in filename.lower() or 'pg' in filename.lower():
                col_type = "academics"
            elif "placement" in filename.lower():
                col_type ="placements"
            else:
                col_type = "activities"
            
            chunks = self.chunkData(content)
            embeddings = self.embedder.embed(chunks)
            self.collections[col_type].add(
                documents = chunks,
                embeddings = embeddings,
                ids = [f"{filename}_{i}" for i in range(len(chunks))],
                metadatas =[{"source":filename}]*len(chunks)
            )
    
    def query(self,query,collection_type,top_k=3):
        try:
            query_embeddings = self.embedder.embed([query])
            results = self.collections[collection_type].query(
                query_embeddings = query_embeddings.tolist(),
                n_results = top_k
            )
            return results["documents"][0]
        except Exception as e:
            print(f"\nQuery Errors:{str(e)}")
            raise

class Mixtral:
    def __init__(self):
        load_dotenv()
        self.LLM = "mistral"  # Changed to Ollama's model name
        # No API key needed for Ollama local setup
        self.client = ollama  # Using ollama directly
    
    def generate(self, prompt, max_new_token=300, temperature=0.1, top_p=0.9):
        try:
            response = self.client.generate(
                model=self.LLM,
                prompt=prompt,
                options={
                    'num_predict': max_new_token,
                    'temperature': temperature,
                    'top_p': top_p
                }
            )
            return response['response'].strip()
        except Exception as e:
            print(f"Mixtral Generation Error: {str(e)}")
            raise RuntimeError("Failed to generate any response. Check the Ollama setup.")

class ThaparAssistant(VectorDB, Mixtral):
    
    def __init__(self):
        VectorDB.__init__(self)
        Mixtral.__init__(self)
        self.populate_db()
        
    def _determineCollectionType(self,query):
        query_lower =query.lower()
        if any(kw in query_lower for kw in ["hostel","room","mess","sharing","hall","accomodation"]):
            return "hostels"
        elif any(kw in query_lower for kw in ["scholarships","fee","course","syllabus","program"]):
            return "academics"
        elif any(kw in query_lower for kw in ["record","package","recruiter","placement"]):
            return "placements"
        else:
            return "activities"
            
    def build_prompt(self, query, context):
        context_str = "\n\n".join([
            f"CONTEXT {i+1}:\n{text}" 
            for i, text in enumerate(context)
        ])
        return f"""You are a helpful assistant for Thapar University with two response modes:

# When context exists:
1. STRICTLY prioritize the provided official context
2. Use exact figures/terms (₹ instead of Rs/INR)
3. Format lists with bullet points
4. For numerical queries, provide exact values only
5. Never hallucinate details - say "Not specified in official records" if unsure

# For general queries:
1. Use your knowledge about Indian universities
2. Clearly mark non-context answers with [General Knowledge]
3. For comparisons, maintain neutrality
4. When estimating, disclose it's an approximation

Current Context:
{context_str if context else 'No specific context provided'}

User Question: {query}

First determine if this is:
A) A specific factual query about Thapar (use context)
B) A general higher-education question (wider knowledge)
C) Administrative (dates/processes - be precise)

Then provide a 1-2 sentence response accordingly, using the format:
[Response Type]: [Your answer]"""
    
    def ask(self, query):
        try:
            col_type = self._determineCollectionType(query)
            context = self.query(query, col_type)
            print(f"\nRETRIEVED CONTEXT FOR '{query}':")
            for i, text in enumerate(context, 1):
                print(f"[Context {i}]: {text[:200]}...")
            prompt = self.build_prompt(query, context)
            response = self.generate(prompt)
            if "Rs" not in response and any("Rs." in ctx for ctx in context):
                response = "Information not found in records"
            return response
        except Exception as e:
            return f"System error: {str(e)}"

assistant = ThaparAssistant()
queries = [
        "List all hostels in Thapar?",
        "What is the mess fee for agira hall ?",
        "Which coding-related societies exist?",
        "Tell me various events that occur in Thapar?",
        "What is the average package for MTECH CSE in Thapar?",
        "Who are the top recruiters for MCA?",
        "Tell me about MSc scholarships for 8.5 CGPA students",
        "What are various computer science societies in IIT Bombay"
]

for query in queries:
    print(f"\n{query}")
    print(f"\n{assistant.ask(query)}")