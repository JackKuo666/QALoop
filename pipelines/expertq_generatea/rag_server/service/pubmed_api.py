"""
PubMed API service using Biopython Entrez - no Elasticsearch required.
"""
import time
from typing import Dict, List
from Bio import Entrez
import requests
from dto.bio_document import PubMedDocument
from utils.bio_logger import bio_logger as logger

# PubMed account pool for API keys (rate limiting)
PUBMED_ACCOUNT = [
    {"email": "email1@gmail.com", "api_key": "60eb67add17f39aa588a43e30bb7fce98809"},
    {"email": "email2@gmail.com", "api_key": "fd9bb5b827c95086b9c2d579df20beca2708"},
    {"email": "email3@gmail.com", "api_key": "026586b79437a2b21d1e27d8c3f339230208"},
    {"email": "email4@gmail.com", "api_key": "bca0489d8fe314bfdbb1f7bfe63fb5d76e09"},
]


class PubMedXmlParse:
    """Parse PubMed XML responses"""

    def parse_pubmed_xml(self, xml_text: str) -> List[Dict]:
        """Parse PubMed XML to extract article information"""
        from io import BytesIO
        from Bio import Entrez

        records = []
        try:
            # Use Biopython's Entrez.read for PubMed XML
            handle = BytesIO(xml_text.encode('utf-8'))
            result = Entrez.read(handle)

            # Entrez.read returns {PubmedArticle: [...], PubmedBookArticle: [...]}
            # or {PubmedArticle: {...}} for single article
            if 'PubmedArticle' in result:
                articles = result['PubmedArticle']
                # Handle single article (dict) vs list
                if isinstance(articles, dict):
                    records = [articles]
                else:
                    records = list(articles)
        except Exception as e:
            logger.error(f"Error parsing PubMed XML: {e}")
        return records


class PubMedApi:
    """PubMed API using Biopython Entrez - no ES required"""

    def __init__(self):
        self.pubmed_xml_parse = PubMedXmlParse()

    def search_database(self, query: str, retmax: int, search_type: str = "keyword") -> List[str]:
        """
        Search PubMed database using Biopython Entrez.

        Args:
            query: Search query
            retmax: Maximum number of results
            search_type: 'keyword' or 'advanced'

        Returns:
            List of PubMed IDs
        """
        start_time = time.time()
        db = "pubmed"

        # Randomly select a PubMed account for rate limiting
        random_index = int((time.time() * 1000) % len(PUBMED_ACCOUNT))
        pubmed_account = PUBMED_ACCOUNT[random_index]
        Entrez.email = pubmed_account["email"]
        Entrez.api_key = pubmed_account["api_key"]

        try:
            if search_type == "keyword":
                # Filter out non-article types
                art_type_list = [
                    "Address", "Bibliography", "Biography", "Books and Documents",
                    "Clinical Conference", "Comment", "Congress", "Dictionary",
                    "Directory", "Editorial", "Guideline", "Interview", "Lecture",
                    "Legal Case", "Letter", "News", "Newspaper Article",
                    "Practice Guideline", "Published Erratum", "Technical Report"
                ]
                art_type = "(" + " OR ".join(f'"{j}"[Filter]' for j in art_type_list) + ")"
                query = f"({query}) AND (fha[Filter]) NOT {art_type}"

            handle = Entrez.esearch(
                db=db, term=query, usehistory="y", sort="relevance", retmax=retmax
            )
            results = Entrez.read(handle)
            id_list = results["IdList"]
            handle.close()

            logger.info(f"PubMed search completed: query={query}, found {len(id_list)} results, took {time.time() - start_time:.2f}s")
            return id_list

        except Exception as e:
            logger.error(f"Error in PubMed search: {e}")
            raise e

    def fetch_details(self, id_list: List[str], db: str = "pubmed", rettype: str = "abstract") -> List[Dict]:
        """
        Fetch article details from PubMed.

        Args:
            id_list: List of PubMed IDs
            db: Database name
            rettype: Return type

        Returns:
            List of article records
        """
        if not id_list:
            return []

        start_time = time.time()
        ids = ",".join(id_list)

        # Randomly select a PubMed account
        random_index = int((time.time() * 1000) % len(PUBMED_ACCOUNT))
        api_key = PUBMED_ACCOUNT[random_index]["api_key"]

        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db={db}&id={ids}&retmode=xml&api_key={api_key}"

        try:
            response = requests.get(url, timeout=30)
            articles = self.pubmed_xml_parse.parse_pubmed_xml(response.text)
            logger.info(f"PubMed fetch details: {len(articles)} articles, took {time.time() - start_time:.2f}s")
            return articles
        except Exception as e:
            logger.error(f"Error fetching PubMed details: {e}")
            return []

    def search(self, query: str, top_k: int, search_type: str = "keyword") -> List[PubMedDocument]:
        """
        Search PubMed and return formatted documents.

        Args:
            query: Search query
            top_k: Number of results
            search_type: Search type

        Returns:
            List of PubMedDocument objects
        """
        start_time = time.time()
        logger.info(f"Searching PubMed: query={query}, top_k={top_k}")

        try:
            id_list = self.search_database(query, retmax=top_k, search_type=search_type)
            records = self.fetch_details(id_list)

            results = []
            for result in records:
                # Entrez.parse structure: {MedlineCitation: {...}, PubmedData: {...}}
                medline = result.get("MedlineCitation", {})
                pubmed_data = result.get("PubmedData", {})

                # Get PMID
                pmid_info = medline.get("PMID", {})
                pmid = pmid_info if isinstance(pmid_info, str) else pmid_info.get("#text", "")

                # Get Article info
                article = medline.get("Article", {})

                # Title
                title = article.get("ArticleTitle", "")

                # Abstract
                abstract_info = article.get("Abstract", {})
                if isinstance(abstract_info, dict):
                    abstract_text = abstract_info.get("AbstractText", "")
                    if isinstance(abstract_text, list):
                        abstract_text = " ".join(str(t) for t in abstract_text)
                else:
                    abstract_text = str(abstract_info) if abstract_info else ""

                # Authors
                author_list = article.get("AuthorList", [])
                authors = self._process_authors(author_list)

                # Journal
                journal_info = medline.get("MedlineJournalInfo", {})
                journal_title = journal_info.get("JournalTitle", "")
                if not journal_title:
                    journal_info = article.get("Journal", {})
                    journal_title = journal_info.get("Title", "")

                # DOI
                doi = ""
                article_ids = pubmed_data.get("ArticleIdList", [])
                for aid in article_ids:
                    if isinstance(aid, dict) and aid.get("IdType") == "doi":
                        doi = aid.get("#text", "")
                        break

                # Publication date
                journal_issue = article.get("Journal", {}).get("JournalIssue", {})
                pub_date_info = journal_issue.get("PubDate", {})
                pub_date = ""
                if isinstance(pub_date_info, dict):
                    year = pub_date_info.get("Year", "")
                    month = pub_date_info.get("Month", "")
                    day = pub_date_info.get("Day", "")
                    pub_date = f"{year}-{month}-{day}" if year else ""

                doc = PubMedDocument(
                    title=title,
                    abstract=abstract_text,
                    authors=authors,
                    doi=doi,
                    source="pubmed",
                    source_id=pmid,
                    pub_date=pub_date,
                    journal=journal_title,
                    text=abstract_text,
                    url=f'https://pubmed.ncbi.nlm.nih.gov/{pmid}'
                )
                results.append(doc)

            logger.info(f"PubMed search completed: {len(results)} documents, took {time.time() - start_time:.2f}s")
            return results

        except Exception as e:
            logger.error(f"Error in PubMed search: {e}")
            raise e

    def _process_authors(self, author_list: List[Dict]) -> str:
        """Process author list into string format"""
        if isinstance(author_list, list):
            return ", ".join([f"{a.get('ForeName', '')} {a.get('LastName', '')}" for a in author_list if a])
        return str(author_list) if author_list else ""
