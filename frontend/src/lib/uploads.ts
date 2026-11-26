/**
 * File types the document library accepts. Keep in step with SUPPORTED_EXTENSIONS
 * in src/agentic_chatbot/utils/document_loader.py: the server rejects anything else.
 *
 * Documents come first because Windows shows this list in the file dialog's
 * "Custom Files" filter, and files not in it are hidden from the dialog.
 */
export const UPLOAD_ACCEPT = [
  '.pdf', '.docx', '.xlsx', '.xlsm', '.xls', '.csv', '.tsv', '.txt', '.md', '.markdown', '.rst', '.json', '.jsonl', '.xml',
  '.yaml', '.yml', '.toml', '.ini', '.cfg', '.log', '.sql', '.html', '.htm', '.css',
  '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.c', '.cpp', '.h', '.hpp',
  '.rb', '.php', '.sh', '.bat', '.ps1', '.r', '.kt', '.swift', '.scala',
].join(',');

export const UPLOAD_TYPES_LABEL = 'PDF, Word, Excel, CSV, text, Markdown, JSON and code';
