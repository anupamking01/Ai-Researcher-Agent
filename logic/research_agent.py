# Description: Research assistant class that handles the research process for a given question.

import asyncio
import json
import os
import uuid

from scrape.web_search import web_search
from scrape.web_scrape import async_browse
from text_preprocess.text import (
    write_to_file,
    create_message,
    create_chat_completion,
    read_txt_files,
    write_md_to_pdf,
)
from settings import Config
from logic import prompts


CFG = Config()


class ResearchAgent:
    def __init__(self, question, agent, agent_role_prompt, websocket):
        """Initialize the research assistant for a single research task."""
        self.question = question
        self.agent = agent
        self.agent_role_prompt = (
            agent_role_prompt
            if agent_role_prompt
            else prompts.generate_agent_role_prompt(agent)
        )
        self.visited_urls = set()
        self.research_summary = ""
        self.directory_name = uuid.uuid4()
        self.dir_path = os.path.dirname(f"./outputs/{self.directory_name}/")
        self.websocket = websocket

    async def summarize(self, text, topic):
        """Summarize text with respect to the requested topic."""
        messages = [create_message(text, topic)]
        await self.websocket.send_json(
            {"type": "logs", "output": f"📝 Summarizing text for query: {topic}"}
        )

        return create_chat_completion(
            model=CFG.fast_llm_model,
            messages=messages,
        )

    async def get_new_urls(self, url_set_input):
        """Return previously unseen URLs while preserving input order."""
        new_urls = []
        for url in url_set_input:
            if not url:
                continue
            if url not in self.visited_urls:
                await self.websocket.send_json(
                    {
                        "type": "logs",
                        "output": f"✅ Adding source url to research: {url}\n",
                    }
                )
                self.visited_urls.add(url)
                new_urls.append(url)

        return new_urls

    async def call_agent(self, action, stream=False, websocket=None):
        messages = [
            {"role": "system", "content": self.agent_role_prompt},
            {"role": "user", "content": action},
        ]
        answer = create_chat_completion(
            model=CFG.smart_llm_model,
            messages=messages,
            stream=stream,
            websocket=websocket,
        )
        return answer

    async def create_search_queries(self):
        """Create focused search queries for the research question."""
        result = await self.call_agent(
            prompts.generate_search_queries_prompt(self.question)
        )
        await self.websocket.send_json(
            {
                "type": "logs",
                "output": (
                    "🧠 I will conduct my research based on the following "
                    f"queries: {result}..."
                ),
            }
        )
        return json.loads(result)

    async def async_search(self, query):
        """Search and browse previously unseen sources for a query.

        Individual browse failures are logged and excluded instead of causing
        the entire research run to fail when the responses are aggregated.
        """
        search_results = json.loads(web_search(query))
        candidate_urls = [
            result.get("href")
            for result in search_results
            if isinstance(result, dict) and result.get("href")
        ]
        new_search_urls = await self.get_new_urls(candidate_urls)

        await self.websocket.send_json(
            {
                "type": "logs",
                "output": (
                    "🌐 Browsing the following sites for relevant information: "
                    f"{new_search_urls}..."
                ),
            }
        )

        if not new_search_urls:
            return []

        tasks = [
            async_browse(url, query, self.websocket) for url in new_search_urls
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        successful_responses = []
        for url, response in zip(new_search_urls, responses):
            if isinstance(response, Exception):
                await self.websocket.send_json(
                    {
                        "type": "logs",
                        "output": (
                            f"⚠️ Could not browse {url}: "
                            f"{type(response).__name__}"
                        ),
                    }
                )
                continue
            if response:
                successful_responses.append(str(response))

        return successful_responses

    async def run_search_summary(self, query):
        """Run retrieval for a query and persist the gathered source text."""
        await self.websocket.send_json(
            {"type": "logs", "output": f"🔎 Running research for '{query}'..."}
        )

        responses = await self.async_search(query)
        result = "\n".join(responses)

        output_path = f"./outputs/{self.directory_name}/research-{query}.txt"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        write_to_file(output_path, result)
        return result

    async def conduct_research(self):
        """Collect source-grounded research context for the question."""
        self.research_summary = (
            read_txt_files(self.dir_path) if os.path.isdir(self.dir_path) else ""
        )

        if not self.research_summary:
            search_queries = await self.create_search_queries()
            for query in search_queries:
                research_result = await self.run_search_summary(query)
                if research_result:
                    self.research_summary += f"{research_result}\n\n"

        await self.websocket.send_json(
            {
                "type": "logs",
                "output": (
                    "Total research words: "
                    f"{len(self.research_summary.split())}"
                ),
            }
        )

        return self.research_summary

    async def create_concepts(self):
        """Create important concepts from the accumulated research context."""
        result = await self.call_agent(
            prompts.generate_concepts_prompt(
                self.question,
                self.research_summary,
            )
        )

        await self.websocket.send_json(
            {
                "type": "logs",
                "output": f"I will research based on the following concepts: {result}\n",
            }
        )
        return json.loads(result)

    async def write_report(self, report_type, websocket):
        """Write and export the final report."""
        report_type_func = prompts.get_report_by_type(report_type)
        await websocket.send_json(
            {
                "type": "logs",
                "output": (
                    f"✍️ Writing {report_type} for research task: "
                    f"{self.question}..."
                ),
            }
        )
        answer = await self.call_agent(
            report_type_func(self.question, self.research_summary),
            stream=True,
            websocket=websocket,
        )

        path = await write_md_to_pdf(
            report_type,
            self.directory_name,
            await answer,
        )

        return answer, path

    async def write_lessons(self):
        """Write lessons on concepts extracted from the research."""
        concepts = await self.create_concepts()
        for concept in concepts:
            answer = await self.call_agent(
                prompts.generate_lesson_prompt(concept),
                stream=True,
                websocket=self.websocket,
            )
            await write_md_to_pdf("Lesson", self.directory_name, await answer)
