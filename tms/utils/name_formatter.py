import re
import frappe

class NameFormatter:
    def format_name(self, raw_name, document_type):
        """
        Format name as 'Given Name + Surname' regardless of source format
        """
        if not raw_name:
            return None
        
        # Clean the name
        name = self._clean_name(raw_name)
        
        # Apply document-specific formatting rules
        if document_type == 'pakistani_passport':
            return self._format_passport_name(name)
        elif document_type == 'saudi_iqama':
            return self._format_iqama_name(name)
        else:
            return self._format_generic_name(name)
    
    def _format_passport_name(self, name):
        """
        Convert passport format 'SURNAME<<GIVEN<NAMES' to 'Given Names Surname'
        """
        # Handle MRZ format: P<PAK<SURNAME<<GIVEN<NAMES
        if '<<' in name:
            parts = name.split('<<')
            if len(parts) >= 2:
                surname = parts[0].replace('P<PAK', '').strip()
                given_names = parts[1].replace('<', ' ').strip()
                return f"{given_names} {surname}".title()
        
        # Handle all caps names
        if name.isupper():
            words = name.split()
            if len(words) >= 2:
                # Assume last word is surname, rest are given names
                given_names = ' '.join(words[:-1])
                surname = words[-1]
                return f"{given_names} {surname}".title()
        
        return name.title()
    
    def _format_iqama_name(self, name):
        """
        Format Iqama names - usually already in correct order
        """
        # Your sample: "MOHAMMAD SHOHEL DULAL MIAH" → "Mohammad Shohel Dulal Miah"
        if name.isupper():
            return name.title()
        return name
    
    def _format_generic_name(self, name):
        """
        Format generic names - assume Western order: Given Name + Surname
        """
        if name.isupper():
            words = name.split()
            if len(words) >= 2:
                # Simple assumption: last word is surname
                given_names = ' '.join(words[:-1])
                surname = words[-1]
                return f"{given_names} {surname}".title()
        
        return name.title()
    
    def _clean_name(self, name):
        """Remove extra characters and clean up name"""
        # Remove special characters but preserve spaces and letters
        name = re.sub(r'[<>]', ' ', name)  # Replace < and > with spaces
        name = re.sub(r'\s+', ' ', name)   # Collapse multiple spaces
        name = name.strip()
        
        # Remove common prefixes/suffixes
        prefixes = ['MR', 'MRS', 'MS', 'DR', 'PROF', 'ENG']
        words = name.split()
        if words and words[0].upper() in prefixes:
            words = words[1:]
        
        return ' '.join(words)