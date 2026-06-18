import asyncio
import httpx
import json

async def query_pubmed(search_term: str):
    try:
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": search_term,
            "retmode": "json",
            "retmax": "5"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(search_url, params=params)
            id_list = res.json().get("esearchresult", {}).get("idlist", [])
            
        if not id_list:
            return []
            
        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        params_summary = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json"
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            res_sum = await client.get(summary_url, params=params_summary)
            results = res_sum.json().get("result", {})
            
        papers = []
        for uid in id_list:
            info = results.get(uid, {})
            title = info.get("title", "")
            if title:
                papers.append(title)
        return papers
    except Exception as e:
        print(f"PubMed error: {e}")
        return []

async def query_crossref(search_term: str):
    try:
        url = "https://api.crossref.org/works"
        params = {
            "query": search_term,
            "rows": "5"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, params=params)
            items = res.json().get("message", {}).get("items", [])
            
        papers = []
        for item in items:
            title_list = item.get("title", [])
            title = title_list[0] if title_list else ""
            if title:
                papers.append(title)
        return papers
    except Exception as e:
        print(f"CrossRef error: {e}")
        return []

async def query_openalex(search_term: str):
    try:
        url = "https://api.openalex.org/works"
        params = {
            "search": search_term,
            "per_page": "5"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"User-Agent": "mailto:surgical-system@example.com"}
            res = await client.get(url, params=params, headers=headers)
            results = res.json().get("results", [])
            
        papers = []
        for item in results:
            title = item.get("display_name") or ""
            if title:
                papers.append(title)
        return papers
    except Exception as e:
        print(f"OpenAlex error: {e}")
        return []

async def main():
    term = "laparoscopic versus open pyloromyotomy in infants"
    print(f"Querying term: {term}")

    pubmed_task = query_pubmed(term)
    crossref_task = query_crossref(term)
    openalex_task = query_openalex(term)

    pubmed, crossref, openalex = await asyncio.gather(pubmed_task, crossref_task, openalex_task)

    print(f"PubMed titles ({len(pubmed)}): {pubmed}")
    print(f"CrossRef titles ({len(crossref)}): {crossref}")
    print(f"OpenAlex titles ({len(openalex)}): {openalex}")

asyncio.run(main())
