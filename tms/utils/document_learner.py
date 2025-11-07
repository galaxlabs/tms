import frappe
import re
import json
from .knowledge_base import DocumentKnowledgeBase

class SelfLearningDocumentClassifier:
    def __init__(self):
        self.knowledge_base = DocumentKnowledgeBase()
        self.document_signatures = self._load_document_signatures()
    
    def _load_document_signatures(self):
        """Load document identifying signatures"""
        return {
            'saudi_iqama': {
                'keywords': ['هوية مقيم', 'رقم الهوية', 'إقامة', 'IQAMA', 'RESIDENT ID'],
                'required_keywords': 2,
                'confidence_threshold': 0.7
            },
            'pakistani_passport': {
                'keywords': ['Islamic Republic of Pakistan', 'PAKISTAN PASSPORT', 'P<PAK', 'Director General'],
                'required_keywords': 2,
                'confidence_threshold': 0.8
            },
            'saudi_visa': {
                'keywords': ['Visa No.', 'رقم الأسرة', 'Kingdom of Saudi Arabia', 'فيزا', 'VISA'],
                'required_keywords': 2,
                'confidence_threshold': 0.7
            },
            'nusuk_card': {
                'keywords': ['NUSUK', 'نُسُك', 'HAJJ', 'UMRAH', 'مكة', 'المدينة'],
                'required_keywords': 2,
                'confidence_threshold': 0.6
            }
        }
    
    def classify_with_learning(self, ocr_text, previous_success_type=None):
        """Classify document and learn from corrections"""
        text_upper = ocr_text.upper()
        
        # Calculate confidence for each document type
        scores = {}
        for doc_type, signature in self.document_signatures.items():
            score = 0
            keyword_matches = 0
            
            for keyword in signature['keywords']:
                if keyword.upper() in text_upper:
                    keyword_matches += 1
                    score += 0.3  # Base score per keyword
            
            # Bonus for reaching required keywords
            if keyword_matches >= signature['required_keywords']:
                score += 0.4
            
            scores[doc_type] = min(score, 1.0)
        
        # Find best match
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        
        # Apply confidence threshold
        threshold = self.document_signatures[best_type]['confidence_threshold']
        
        if best_score >= threshold:
            frappe.logger().info(f"🎯 Document classified as: {best_type} (confidence: {best_score:.2f})")
            return best_type
        else:
            # If low confidence, use previous success type or default
            if previous_success_type and previous_success_type in self.document_signatures:
                frappe.logger().info(f"🤔 Low confidence, using previous: {previous_success_type}")
                return previous_success_type
            else:
                frappe.logger().info("❓ Unknown document type, using generic")
                return 'generic_document'
    
    def learn_from_user_correction(self, original_doc_type, corrected_doc_type, ocr_text):
        """Learn when user corrects document classification"""
        if original_doc_type != corrected_doc_type:
            # Document was misclassified - learn from this
            frappe.logger().info(f"📚 Learning: {original_doc_type} → {corrected_doc_type}")
            
            # Extract new keywords from this document for the correct type
            new_keywords = self._extract_potential_keywords(ocr_text)
            
            # Update knowledge base with new keywords
            self._update_document_signature(corrected_doc_type, new_keywords)
    
    def _extract_potential_keywords(self, text):
        """Extract potential keywords from document text"""
        lines = text.split('\n')
        keywords = []
        
        for line in lines:
            line = line.strip()
            if len(line) > 10 and len(line) < 100:  # Reasonable length for keywords
                # Look for lines with mixed Arabic/English or specific patterns
                if any(indicator in line for indicator in ['No.', 'رقم', 'تاريخ', 'Date']):
                    keywords.append(line)
                elif re.search(r'[A-Z]{2,} [A-Z]{2,}', line):  # Uppercase words
                    keywords.append(line)
                elif re.search(r'[\u0600-\u06FF]{3,} [\u0600-\u06FF]{3,}', line):  # Arabic words
                    keywords.append(line)
        
        return keywords[:5]  # Return top 5 potential keywords
    
    def _update_document_signature(self, doc_type, new_keywords):
        """Update document signature with new learned keywords"""
        if doc_type in self.document_signatures:
            current_keywords = self.document_signatures[doc_type]['keywords']
            
            # Add new keywords (avoid duplicates)
            for keyword in new_keywords:
                if keyword not in current_keywords:
                    current_keywords.append(keyword)
                    frappe.logger().info(f"🔍 Added new keyword for {doc_type}: {keyword}")
            
            # Keep only recent keywords (limit to 20)
            self.document_signatures[doc_type]['keywords'] = current_keywords[-20:]