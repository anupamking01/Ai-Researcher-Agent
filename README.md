# AI Research Agent

Designed to handle a myriad of online research tasks with ease, AI Research Agent is your go-to for generating in-depth, objective, and precise research reports. Tailor your inquiries with advanced customization options to zero in on the most relevant resources, structured outlines, and actionable insights.It sidesteps traditional limitations by executing multiple processes in parallel, significantly outpacing the conventional sequential methods.



## Loom Video
 - [Live Demo 1](https://www.loom.com/share/8c2be0f1afec491d8c1399da0fb50f47?sid=2cb8877f-ddfc-479c-ae52-9a84c145cdba)
 - [Live Demo 2](https://www.loom.com/share/81ebdeb4f0004f4c94164d61266a4b09?sid=a7e69af2-c251-4e5e-bc02-3393d5e252bf)


# The Case for an AI Research Agent
## Why invest in an AI Research Agent? Here are compelling reasons:

**Time Efficiency**: Manual research tasks often stretch into weeks as you sift through resources to form objective conclusions. An AI Research Agent can streamline this process, delivering results in a fraction of the time.

**Accuracy Beyond Limitations**: Traditional Large Language Models (LLMs) rely on historical data, making them prone to inaccuracies and outdated insights. An AI Research Agent circumvents these pitfalls by accessing the most current information, reducing the risk of errors and "hallucinations."

**Expanded Resource Access**: While solutions like ChatGPT with a web plugin might tap into a narrow set of resources, potentially leading to superficial or biased conclusions, an AI Research Agent utilizes a broader and more diverse array of sources. This comprehensive approach helps mitigate bias and enhances the depth of the research.

**Balanced Perspectives**: Relying solely on a limited selection of resources can skew the outcomes of research. An AI Research Agent ensures a more balanced and equitable consideration of available data, leading to more accurate and fair conclusions.

## Overview
**The architecture of our system is strategically designed to optimize research efficiency and accuracy. It employs two specialized types of agents: the "planner" and the "execution" agents. Here’s how they work together**:

**Planner Agent**: This agent acts as the brain of the operation. It formulates specific research questions that guide the entire research process, setting the stage for targeted information gathering.

**Execution Agents**: Once the planner sets the research questions, execution agents spring into action. Their role is to scour for and retrieve the most relevant information pertaining to each question. This ensures that all gathered data is directly aligned with the research objectives.

**Integration and Reporting**: After the execution agents have collected the information, the planner takes over again. It critically assesses, filters, and synthesizes the data, compiling it into a comprehensive research report that is both informative and easy to digest.

**Technological Backbone**: To power these processes, the agents utilize advanced models such as gpt-3.5-turbo-16k and gpt-4. This combination allows them to handle complex research tasks with enhanced speed and accuracy, leveraging the best of what AI technology has to offer.


More specifcally:
* Generate a set of research questions that together form an objective opinion on any given task. 
* For each research question, trigger a crawler agent that scrapes online resources for information relevant to the given task.
* For each scraped resources, summarize based on relevant information and keep track of its sources.
* Finally, filter and aggregate all summarized sources and generate a final research report.

## Key Features of AI Research Agent
Explore the powerful capabilities of AI Research Agent, designed to enhance your research efficiency and quality:

1. **Comprehensive Report Generation:** Automatically create detailed research reports, outlines, resources, and lesson plans tailored to your specific needs.
2. **Robust Data Aggregation:** Harnesses information from over 20 web sources for each research query, ensuring objective and factual conclusions.
3. **User-Friendly Interface:** Features a sleek, easy-to-navigate web interface built with HTML, CSS, and JavaScript, making research accessible to everyone.
4. **Advanced Web Scraping:** Efficiently scrapes web sources, including those with JavaScript, to gather the most relevant and up-to-date information.
5. **Efficient Source Management:** Maintains a detailed log of all visited and utilized web sources, ensuring transparency and repeatability in research processes.
6. **Flexible Export Options:** Offers the convenience of exporting your research reports into PDF format and other popular file types for easy sharing and presentation.
These features are designed to streamline your research process, making it more efficient and effective.


## Commands

<br />

> **Step 1** - clone the project

```bash
$ git clone https://github.com/anupamking01/Ai-Researcher-Agent.git
$ cd Ai-Researcher-Agent
```

<br />

> **Step 2** - Install requirements
```bash
$ pip install -r requirements.txt
```
<br />

> **Step 3** - Create .env file with your OpenAI Key or simply export it

```bash
$ export OPENAI_API_KEY={Your API Key here}
```

<br />

> **Step 4** - Run the agent with FastAPI

```bash
$ uvicorn app:app --reload
```
<br />

> **Step 5** - Go to http://localhost:8000

## 🛡 Conclusion


1. **Fact Accuracy through Extensive Scraping:** Our system is designed to minimize factual errors by scraping a large number of sites—20 per research query. This extensive approach drastically lowers the likelihood of encountering incorrect information.

2. **Bias Reduction, Not Elimination:** While completely eliminating bias is challenging, our goal is to significantly reduce it. We encourage community engagement to enhance the interactions between humans and language learning models, striving for the most effective outcomes.

3. **Diverse Perspectives in Research:** Inherent biases often color research, as individuals may have preconceived opinions on their topics of interest. Our tool addresses this by scraping a wide range of opinions and presenting a balanced view that might otherwise be overlooked by a biased researcher.

4. **Token Usage and Cost Awareness with GPT-4:**
Please be aware that using the GPT-4 model can incur significant costs due to token consumption. By using GPT Researcher, you accept the responsibility to monitor and manage your token usage and related expenses actively. We strongly recommend regularly checking your OpenAI API usage and setting appropriate limits or alerts to avoid unexpected charges.






