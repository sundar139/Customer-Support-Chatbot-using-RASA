import pandas as pd
import json
import yaml
from pathlib import Path
import re

class BitextProcessor:
    def __init__(self, csv_path):
        self.csv_path = csv_path
        self.df = None
        self.intent_mapping = {
            'order_status': 'ask_order_status',
            'track_order': 'ask_order_status',
            'delivery_options': 'ask_shipping_info',
            'shipping_address': 'ask_shipping_info',
            'return': 'initiate_return',
            'return_policy': 'ask_return_policy',
            'refund': 'ask_refund_status',
            'payment_issue': 'ask_payment_issue',
            'contact': 'out_of_scope',
            'greeting': 'greet',
            'thanks': 'thank',
            'goodbye': 'goodbye'
        }
    
    def load_data(self):
        print("Loading Bitext dataset...")
        self.df = pd.read_csv(self.csv_path)
        print(f"Loaded {len(self.df)} rows")
        print(f"Columns: {self.df.columns.tolist()}")
        return self.df
    
    def map_intent(self, original_intent):
        original_intent_lower = str(original_intent).lower().replace(' ', '_')
        
        for key, value in self.intent_mapping.items():
            if key in original_intent_lower:
                return value
        
        if 'order' in original_intent_lower:
            return 'ask_order_status'
        elif 'return' in original_intent_lower:
            return 'initiate_return'
        elif 'ship' in original_intent_lower or 'deliver' in original_intent_lower:
            return 'ask_shipping_info'
        elif 'refund' in original_intent_lower:
            return 'ask_refund_status'
        elif 'payment' in original_intent_lower:
            return 'ask_payment_issue'
        
        return 'out_of_scope'

    def extract_entities(self, text):
        entities = []
        
        order_id_pattern = r'\b\d{5}\b'
        matches = re.finditer(order_id_pattern, text)
        for match in matches:
            entities.append({
                'entity': 'order_id',
                'value': match.group(),
                'start': match.start(),
                'end': match.end()
            })
        
        return entities

    def annotate_text_with_entities(self, text, entities):
        """Return text annotated with inline entity marks like [value](entity).
        Entities are provided with absolute character offsets (start/end).
        """
        if not entities:
            return text
        # Sort entities by start index to build annotated text left-to-right
        entities_sorted = sorted(entities, key=lambda e: e['start'])
        annotated = []
        cursor = 0
        for ent in entities_sorted:
            start = int(ent.get('start', 0))
            end = int(ent.get('end', start))
            value = str(ent.get('value', text[start:end]))
            ent_type = str(ent.get('entity', 'entity'))
            # Append text before the entity
            if cursor < start:
                annotated.append(text[cursor:start])
            # Append annotated entity
            annotated.append(f"[{value}]({ent_type})")
            cursor = end
        # Append any remaining text
        if cursor < len(text):
            annotated.append(text[cursor:])
        return ''.join(annotated)

    def examples_to_block(self, examples):
        """Convert list of examples (str or {'text','entities'}) to block string for YAML.
        Each example line is prefixed with '- '. Entities are inlined.
        """
        lines = []
        for ex in examples:
            if isinstance(ex, str):
                line = f"- {ex}"
            elif isinstance(ex, dict):
                text = str(ex.get('text', ''))
                ents = ex.get('entities', [])
                annotated = self.annotate_text_with_entities(text, ents)
                line = f"- {annotated}"
            else:
                # Fallback: stringify
                line = f"- {str(ex)}"
            lines.append(line)
        # Join with newlines to produce a multi-line scalar; yaml.dump will use '|'
        return "\n".join(lines)
    
    def create_nlu_data(self, sample_size=None):
        print("\nCreating NLU training data...")
        
        if sample_size:
            df_sample = self.df.sample(n=min(sample_size, len(self.df)), random_state=42)
        else:
            df_sample = self.df
        
        nlu_data = {'version': '3.1', 'nlu': []}
        intent_groups = {}
        
        for _, row in df_sample.iterrows():
            try:
                utterance_col = 'utterance' if 'utterance' in self.df.columns else 'instruction'
                intent_col = 'intent' if 'intent' in self.df.columns else 'category'
                
                utterance = str(row[utterance_col]).strip()
                original_intent = str(row[intent_col])
                
                mapped_intent = self.map_intent(original_intent)
                
                if mapped_intent not in intent_groups:
                    intent_groups[mapped_intent] = []
                
                entities = self.extract_entities(utterance)
                
                if entities:
                    example = {'text': utterance, 'entities': entities}
                else:
                    example = utterance
                
                intent_groups[mapped_intent].append(example)
            
            except Exception as e:
                print(f"Error processing row: {e}")
                continue
        
        for intent, examples in intent_groups.items():
            unique_examples = []
            seen = set()
            for ex in examples:
                ex_text = ex if isinstance(ex, str) else ex['text']
                if ex_text not in seen:
                    seen.add(ex_text)
                    unique_examples.append(ex)
            
            nlu_data['nlu'].append({
                'intent': intent,
                'examples': unique_examples[:50]
            })
        
        print(f"Created training data for {len(intent_groups)} intents")
        for intent, examples in intent_groups.items():
            print(f"  - {intent}: {len(examples)} examples")
        
        return nlu_data
    
    def create_response_data(self):
        print("\nCreating response templates...")
        
        responses = {}
        response_col = 'response' if 'response' in self.df.columns else 'response_text'
        intent_col = 'intent' if 'intent' in self.df.columns else 'category'
        
        if response_col in self.df.columns:
            for _, row in self.df.iterrows():
                try:
                    original_intent = str(row[intent_col])
                    mapped_intent = self.map_intent(original_intent)
                    response_text = str(row[response_col]).strip()
                    
                    if mapped_intent not in responses:
                        responses[mapped_intent] = []
                    
                    if response_text and response_text not in responses[mapped_intent]:
                        responses[mapped_intent].append(response_text)
                
                except:
                    continue
        
        return responses
    
    def save_nlu_data(self, output_path, nlu_data):
        print(f"\nSaving NLU data to {output_path}...")
        # Transform examples to block strings expected by Rasa
        transformed = {
            'version': nlu_data.get('version', '3.1'),
            'nlu': []
        }
        for item in nlu_data.get('nlu', []):
            intent = item.get('intent')
            examples = item.get('examples', [])
            block = self.examples_to_block(examples)
            transformed['nlu'].append({'intent': intent, 'examples': block})

        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(transformed, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print("NLU data saved successfully!")
    
    def save_responses(self, output_path, responses):
        print(f"\nSaving responses to {output_path}...")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(responses, f, indent=2, ensure_ascii=False)
        print("Responses saved successfully!")


def main():
    csv_file = Path('dataset') / 'Bitext_Sample_Customer_Support_Training_Dataset.csv'
    
    if not csv_file.exists():
        print(f"ERROR: Dataset file not found at {csv_file}")
        print("Please download the Bitext dataset from Kaggle and place it in the dataset folder.")
        print("Expected filename: bitext-customer-support-llm-chatbot-training-dataset.csv")
        return
    
    processor = BitextProcessor(csv_file)
    
    df = processor.load_data()
    
    nlu_data = processor.create_nlu_data(sample_size=500)
    
    responses = processor.create_response_data()
    
    processor.save_nlu_data('data/nlu_from_bitext.yml', nlu_data)
    processor.save_responses('dataset/bitext_responses.json', responses)
    
    print("\n" + "="*50)
    print("Dataset processing complete!")
    print("="*50)
    print(f"\nNext steps:")
    print("1. Review data/nlu_from_bitext.yml")
    print("2. Merge with data/nlu.yml if needed")
    print("3. Train the model: rasa train")


if __name__ == "__main__":
    main()