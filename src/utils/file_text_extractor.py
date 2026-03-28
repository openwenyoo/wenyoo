"""
File Text Extraction Utility for Form File Uploads.

Extracts text content from various file formats:
- Plain text (.txt)
- Markdown (.md)
- PDF (.pdf)
- CSV (.csv)
- JSON (.json)
"""

import base64
import io
import json
import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class FileTextExtractor:
    """Extracts text content from uploaded files."""
    
    # Supported MIME types and their handlers
    SUPPORTED_TYPES = {
        "text/plain": "extract_text",
        "text/markdown": "extract_text",
        "text/csv": "extract_text",
        "application/json": "extract_json",
        "application/pdf": "extract_pdf",
    }
    
    # File extension to MIME type mapping
    EXTENSION_MAP = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".csv": "text/csv",
        ".json": "application/json",
        ".pdf": "application/pdf",
    }
    
    def __init__(self, max_text_length: int = 100000, max_size_mb: float = 20.0):
        """
        Initialize the file text extractor.
        
        Args:
            max_text_length: Maximum characters to extract from a file
            max_size_mb: Maximum file size in megabytes
        """
        self.max_text_length = max_text_length
        self.max_size_mb = max_size_mb
    
    def get_mime_type_from_extension(self, filename: str) -> Optional[str]:
        """Get MIME type from file extension."""
        if not filename:
            return None
        ext = filename.lower()
        if '.' in ext:
            ext = '.' + ext.rsplit('.', 1)[-1]
        return self.EXTENSION_MAP.get(ext)
    
    def is_supported(self, mime_type: str) -> bool:
        """Check if a MIME type is supported."""
        return mime_type in self.SUPPORTED_TYPES
    
    def extract_text_from_base64(
        self, 
        base64_data: str, 
        mime_type: str,
        filename: Optional[str] = None,
        max_length: Optional[int] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text from base64-encoded file data.
        
        Args:
            base64_data: Base64-encoded file content
            mime_type: MIME type of the file
            filename: Original filename
            max_length: Override max text length for this extraction
            
        Returns:
            Tuple of (extracted_text, metadata_dict)
            
        Raises:
            ValueError: If file type is not supported or file is too large
        """
        # Decode base64
        try:
            file_bytes = base64.b64decode(base64_data)
        except Exception as e:
            raise ValueError(f"Invalid base64 data: {e}")
        
        return self.extract_text_from_bytes(file_bytes, mime_type, filename, max_length)
    
    def extract_text_from_bytes(
        self,
        file_bytes: bytes,
        mime_type: str,
        filename: Optional[str] = None,
        max_length: Optional[int] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text from file bytes.
        
        Args:
            file_bytes: Raw file content
            mime_type: MIME type of the file
            filename: Original filename
            max_length: Override max text length for this extraction
            
        Returns:
            Tuple of (extracted_text, metadata_dict)
            
        Raises:
            ValueError: If file type is not supported or file is too large
        """
        # Check file size
        file_size = len(file_bytes)
        max_bytes = int(self.max_size_mb * 1024 * 1024)
        if file_size > max_bytes:
            raise ValueError(f"File size ({file_size / 1024 / 1024:.2f} MB) exceeds limit ({self.max_size_mb} MB)")
        
        # Determine MIME type from filename if not provided
        if not mime_type and filename:
            mime_type = self.get_mime_type_from_extension(filename)
        
        if not mime_type or mime_type not in self.SUPPORTED_TYPES:
            raise ValueError(f"Unsupported file type: {mime_type}")
        
        # Get the handler method
        handler_name = self.SUPPORTED_TYPES[mime_type]
        handler = getattr(self, f"_{handler_name}", None)
        
        if not handler:
            raise ValueError(f"No handler for MIME type: {mime_type}")
        
        # Extract text
        effective_max_length = max_length or self.max_text_length
        extracted_text = handler(file_bytes, effective_max_length)
        
        # Build metadata
        metadata = {
            "original_filename": filename,
            "file_type": mime_type,
            "file_size": file_size,
            "extracted_length": len(extracted_text),
            "truncated": len(extracted_text) >= effective_max_length
        }
        
        return extracted_text, metadata
    
    def _extract_text(self, file_bytes: bytes, max_length: int) -> str:
        """Extract text from plain text, markdown, or CSV files."""
        try:
            # Try UTF-8 first
            text = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                # Fallback to latin-1
                text = file_bytes.decode('latin-1')
            except UnicodeDecodeError:
                # Last resort: ignore errors
                text = file_bytes.decode('utf-8', errors='ignore')
        
        # TODO: Replace simple truncation with chunked extraction/summarization for larger imports.
        # Truncate if needed
        if len(text) > max_length:
            text = text[:max_length]
            # Try to truncate at a word boundary
            last_space = text.rfind(' ', max_length - 100, max_length)
            if last_space > max_length - 100:
                text = text[:last_space] + "..."
        
        return text.strip()
    
    def _extract_json(self, file_bytes: bytes, max_length: int) -> str:
        """Extract text from JSON files - convert to formatted string."""
        try:
            text = file_bytes.decode('utf-8')
            data = json.loads(text)
            # Pretty print the JSON
            formatted = json.dumps(data, ensure_ascii=False, indent=2)
            
            if len(formatted) > max_length:
                formatted = formatted[:max_length] + "\n... (truncated)"
            
            return formatted
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to parse JSON: {e}")
            # Fall back to plain text extraction
            return self._extract_text(file_bytes, max_length)
    
    def _extract_pdf(self, file_bytes: bytes, max_length: int) -> str:
        """Extract text from PDF files."""
        try:
            # Try pypdf first (formerly PyPDF2)
            try:
                from pypdf import PdfReader
            except ImportError:
                try:
                    from PyPDF2 import PdfReader
                except ImportError:
                    # Try pdfplumber as fallback
                    try:
                        import pdfplumber
                        return self._extract_pdf_pdfplumber(file_bytes, max_length)
                    except ImportError:
                        raise ImportError(
                            "No PDF library available. Install one of: "
                            "pypdf, PyPDF2, or pdfplumber"
                        )
            
            # Use pypdf/PyPDF2
            pdf_file = io.BytesIO(file_bytes)
            reader = PdfReader(pdf_file)
            
            text_parts = []
            total_length = 0
            
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
                total_length += len(page_text)
                
                if total_length >= max_length:
                    break
            
            full_text = "\n".join(text_parts)
            
            if len(full_text) > max_length:
                full_text = full_text[:max_length]
                # Try to truncate at a sentence boundary
                last_period = full_text.rfind('.', max_length - 200, max_length)
                if last_period > max_length - 200:
                    full_text = full_text[:last_period + 1] + "\n... (truncated)"
            
            return full_text.strip()
            
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            raise ValueError(f"Failed to extract text from PDF: {e}")
    
    def _extract_pdf_pdfplumber(self, file_bytes: bytes, max_length: int) -> str:
        """Extract text from PDF using pdfplumber."""
        import pdfplumber
        
        pdf_file = io.BytesIO(file_bytes)
        text_parts = []
        total_length = 0
        
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
                total_length += len(page_text)
                
                if total_length >= max_length:
                    break
        
        full_text = "\n".join(text_parts)
        
        if len(full_text) > max_length:
            full_text = full_text[:max_length] + "\n... (truncated)"
        
        return full_text.strip()


# Global instance for convenience
_default_extractor: Optional[FileTextExtractor] = None


def get_file_extractor(
    max_text_length: int = 100000, 
    max_size_mb: float = 20.0
) -> FileTextExtractor:
    """Get or create the global file text extractor instance."""
    global _default_extractor
    if _default_extractor is None:
        _default_extractor = FileTextExtractor(max_text_length, max_size_mb)
    return _default_extractor


def extract_text_from_file(
    base64_data: str,
    mime_type: str,
    filename: Optional[str] = None,
    max_length: int = 100000
) -> Tuple[str, Dict[str, Any]]:
    """
    Convenience function to extract text from a base64-encoded file.
    
    Args:
        base64_data: Base64-encoded file content
        mime_type: MIME type of the file
        filename: Original filename
        max_length: Maximum characters to extract
        
    Returns:
        Tuple of (extracted_text, metadata_dict)
    """
    extractor = get_file_extractor()
    return extractor.extract_text_from_base64(base64_data, mime_type, filename, max_length)
