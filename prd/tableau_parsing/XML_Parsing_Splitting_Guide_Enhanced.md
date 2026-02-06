# Comprehensive Guide: XML Parsing and Splitting for RAG Vector Databases and Knowledge Graphs
## Enhanced with Deep Research Analysis (2024-2025)

## Executive Summary

This document synthesizes comprehensive research on parsing and splitting XML files for two primary use cases:
1. **RAG (Retrieval-Augmented Generation) Vector Databases** - Converting XML into semantically meaningful chunks for vector embeddings
2. **Knowledge Graph Construction** - Extracting entities, relationships, and attributes from XML to build structured knowledge graphs

**Key 2024-2025 Findings:**
- **Markdown as Intermediate Representation**: Converting XML to Markdown prior to chunking significantly improves RAG retrieval accuracy by reducing token noise while preserving semantic hierarchy
- **Hierarchical Retrieval**: The "Parent-Child" chunking strategy is optimal for deeply nested XML structures
- **Hybrid KG Construction**: The most robust pipelines combine RML (RDF Mapping Language) for deterministic structure with LLMs for entity disambiguation
- **Tooling Shift**: IBM's **Docling** and **Unstructured.io** have emerged as dominant preprocessing libraries

---

## Table of Contents

1. [XML Parsing Fundamentals](#xml-parsing-fundamentals)
2. [XML for RAG Vector Databases](#xml-for-rag-vector-databases)
3. [XML for Knowledge Graph Construction](#xml-for-knowledge-graph-construction)
4. [XML to Markdown Conversion](#xml-to-markdown-conversion)
5. [Best Practices and Recommendations](#best-practices-and-recommendations)
6. [Tools and Libraries (2024-2025)](#tools-and-libraries-2024-2025)
7. [Implementation Examples](#implementation-examples)

---

## XML Parsing Fundamentals

### Parser Types

**1. SAX (Simple API for XML)**
- **Characteristics**: Event-driven, memory-efficient
- **Best For**: Large XML files, streaming processing
- **Trade-offs**: Requires more code to manage state and relationships
- **Use Case**: Processing very large XML documents where memory is a concern

**2. DOM (Document Object Model)**
- **Characteristics**: Loads entire document into memory as a tree structure
- **Best For**: Small to medium files, complex navigation needs
- **Trade-offs**: Memory-intensive for large files, easier to navigate
- **Use Case**: When you need to traverse the document structure multiple times

**3. lxml (Python)**
- **Characteristics**: Combines C speed with Python ease of use
- **Best For**: General-purpose XML processing in Python
- **Advantages**: 
  - Offers both SAX and DOM-like functionalities
  - More tolerant of malformed XML
  - Excellent namespace handling
- **Recommendation**: Generally recommended for Python-based projects

**4. Pygixml (2025)**
- **Characteristics**: High-performance XML parser for Python, built on `pugixml` (C++)
- **Best For**: Massive XML files requiring maximum performance
- **Advantages**: Outperforms `lxml` for large datasets, offers XPath support
- **Use Case**: Preprocessing large datasets before chunking

### Key Considerations

- **Namespace Handling**: XML documents often use namespaces. Ensure your parser is namespace-aware
- **Error Handling**: Implement robust error handling for malformed XML
- **Character Encoding**: Correctly handle encoding (UTF-8, ISO-8859-1, etc.)
- **Data Cleaning**: Remove unnecessary whitespace, HTML tags, and special characters
- **Metadata Extraction**: Identify and extract relevant metadata from attributes and tags

---

## XML for RAG Vector Databases

### Overview

RAG systems enhance LLM responses by retrieving relevant external knowledge. The goal is to create meaningful chunks of text that can be embedded into vectors and efficiently retrieved based on user queries.

### The Parent-Child Indexing Pattern (2025 Best Practice)

For XML documents, the **Parent-Child** (or Hierarchical) indexing strategy is widely regarded as the most effective method for preserving context.

**Mechanism:**
- Document is split into granular "child" chunks (e.g., individual XML elements or leaf nodes) which are embedded and indexed
- These child nodes retain a reference to a larger "parent" chunk (e.g., the containing `<section>` or the entire document)
- When a query matches a child node's vector, the system retrieves the *parent* node's text for the LLM context window

**Benefits:**
- Decouples the *retrieval unit* (which needs to be specific and semantic) from the *generation unit* (which needs context and flow)
- Maintains context while allowing precise semantic matching
- Libraries like LlamaIndex implement this via `HierarchicalNodeParser`, which creates a tree of nodes where children link to parents

**Implementation:**
```python
from llama_index.core.node_parser import HierarchicalNodeParser
from llama_index.core.retrievers import AutoMergingRetriever

# Create hierarchical nodes
node_parser = HierarchicalNodeParser.from_defaults(
    chunk_sizes=[2048, 512, 128]  # Parent, child, grandchild sizes
)

# Use AutoMergingRetriever to merge siblings into parent if needed
retriever = AutoMergingRetriever(
    vector_store_index.as_retriever(similarity_top_k=6),
    storage_context=storage_context,
    verbose=True
)
```

### Chunking Strategies

#### 1. Element-Based Chunking (XML-Specific)
- Split XML documents based on specific XML elements
- Example: Each `<article>` element becomes a chunk
- **Pros**: Preserves document structure, maintains semantic boundaries
- **Cons**: May create chunks of varying sizes
- **Best For**: Highly structured data (e.g., product catalogs, patent data) where tags strictly define independent units

#### 2. Semantic Chunking
- Uses embeddings to find natural semantic boundaries
- Groups semantically similar content together
- **Mechanism**: Text is segmented into sentences. Embeddings are generated for adjacent groups. If cosine similarity drops below a threshold, a split occurs
- **Pros**: Maintains contextual coherence, improves retrieval accuracy
- **Cons**: Computationally expensive, may break apart structured lists or tables
- **Best For**: Narrative XML content (e.g., news feeds, book chapters) where the flow of ideas matters more than tag structure

#### 3. Hierarchical (Recursive) Chunking
- Splits text based on a hierarchy of separators (H1/Section → H2/Subsection → Paragraphs)
- **Pros**: Balances structure and size, respects document's logical skeleton
- **Cons**: Can result in context loss if a child chunk is separated from its parent header (mitigated by Parent-Child indexing)
- **Best For**: Technical documentation, legal codes, complex manuals. **Currently the industry standard** for general RAG applications

#### 4. Path-Aware Chunking
- XML elements often derive meaning from their path (e.g., `<price>` inside `<premium_product>` vs. `<budget_product>`)
- **Breadcrumb Injection**: Inject the XPath or a breadcrumb string into the text of the chunk
- **Metadata Enrichment**: Store structural path as metadata for pre-filtering in vector database

### Metadata Management vs. Embedding Tags

A critical decision in RAG pipelines is whether to include XML tags in the vector embedding or to strip them.

| Strategy | Description | Pros | Cons | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **Embed Tags** | Include `<tag>content</tag>` in the vector | Preserves explicit boundaries; some LLMs understand XML tags | High token overhead; "noise" can dilute semantic density | **Avoid** for deep hierarchies; Use only for shallow, semantic tags |
| **Strip Tags** | Remove tags, keep content only | High token efficiency; clean semantic signal | Loss of context (e.g., distinguishing "Author" from "Subject") | **Use** only if context is injected via text prefixes |
| **Metadata Extraction** | Extract attributes/tags to Vector DB metadata fields | Enables precise filtering; clean embeddings | Requires complex preprocessing pipeline | **Best Practice** |

**Best Practice:** Use **Metadata Extraction**. Attributes such as `id`, `date`, `author`, and `category` should be extracted from XML attributes and stored as distinct fields in the vector database. This enables "Hybrid Search" where a keyword or metadata filter is applied first, followed by a vector search on the clean text content.

### Best Practices for RAG

**Chunk Size Optimization:**
- Start with 200-400 tokens per chunk for most applications
- Experiment with different sizes based on your data and embedding model
- Consider token limits of your embedding model

**Context Preservation:**
- Include parent element context (e.g., article title with paragraph)
- Preserve section boundaries - never split across sections
- Use overlapping windows (50-100 tokens) to maintain context transitions
- Implement Parent-Child indexing for hierarchical structures

**Metadata Enrichment:**
- Store metadata alongside text chunks in vector database
- Include: element name, attribute values, file name, section heading, XPath
- Enable filtering and ranking based on metadata

**Hybrid Retrieval:**
- Combine vector similarity search with keyword-based filtering
- Use metadata filters to narrow search space before vector search
- Improves both recall and precision

---

## XML for Knowledge Graph Construction

### Overview

Knowledge graphs represent information as entities (nodes) connected by relationships (edges), with attributes (properties) attached to entities. Converting XML to knowledge graphs involves extracting this structured information.

### Key Components

#### 1. Entity Extraction
- **Named Entity Recognition (NER)**: Identify entities from text content
- **XML Element Mapping**: Map XML elements to entity types
- **Entity Disambiguation**: Merge duplicate entities

#### 2. Relationship Extraction
- **Structural Relationships**: Extract from XML hierarchy (parent-child elements)
- **Attribute-Based Relationships**: Extract from XML attributes
- **Semantic Relationships**: Use NLP/LLM to identify relationships in text content

#### 3. Attribute Extraction
- Extract attribute values from XML attributes
- Extract text content from XML elements as properties
- Preserve data types and constraints

### Conversion Approaches

#### Approach 1: Direct XML to RDF Mapping (RML) - The Deterministic Approach

The **RDF Mapping Language (RML)** remains the gold standard for converting semi-structured data (XML, JSON, CSV) into RDF triples. RML extends R2RML to support hierarchical sources.

**Workflow:**
1. An RML mapping file defines `LogicalSources` (XPath iterators) and `SubjectMap`/`PredicateObjectMap` pairs
2. RML engine executes the mapping to generate RDF triples
3. Validate generated RDF against domain ontology (e.g., SHACL shapes)

**Advantages:**
- Deterministic, traceable, and hallucination-free
- If the XML schema is known and stable, RML guarantees 100% precision

**Limitations:**
- Creating RML mappings is labor-intensive and requires deep knowledge of Semantic Web technologies
- Brittle to schema changes

**2025 Updates:**
- New engines like **CARML** and **RMLMapper** have improved support for complex XML namespaces
- Functions (FnO) for data transformation during mapping

#### Approach 2: LLM-Based Extraction - The Generative Approach

LLMs are increasingly used to bypass rigid mappings by directly extracting triples `(Subject, Predicate, Object)` from XML content.

**Zero-Shot Extraction:**
- Prompting an LLM with the XML content and a target ontology to generate triples
- Schema-Agnostic: Excels when the XML schema is unknown, variable, or extremely complex

**Challenges:**
- LLMs may hallucinate relationships or fail to strictly adhere to the target ontology
- May use `hasAuthor` instead of `dc:creator`

**Tools:**
- **Neo4j's LLM Knowledge Graph Builder**: Automates extraction with features for "Community Summarization" (GraphRAG)
- **LangChain's GraphTransformer**: Facilitates pipeline for converting unstructured text within XML tags into graph structures

#### Approach 3: Hybrid Approaches - The 2025 Standard (Neuro-Symbolic)

The most advanced pipelines employ a **Neuro-Symbolic** or Hybrid approach, combining the reliability of RML with the flexibility of LLMs.

**1. LLM-Generated RML:**
- Instead of writing RML manually, developers use LLMs to *generate* the RML mapping files based on a sample XML and target ontology
- This "Code Generation" approach ensures the runtime execution is deterministic (via the RML engine) while reducing the setup effort

**2. LLM-Enhanced RML:**
- RML rules are used for the structural skeleton (e.g., mapping `<person>` to `foaf:Person`)
- LLMs are called via User Defined Functions (UDFs) within the mapping to process unstructured text fields (e.g., extracting entities from a `<description>` tag)

**3. Ontology Alignment:**
- LLMs are used to map the XML schema elements to ontology classes, creating a "conceptual mapping" that is then translated into technical RML rules

**Benefits:**
- Combines precision of rule-based mapping with flexibility of LLM extraction
- Mitigates hallucination risks of pure LLM extraction
- Maintains structural guarantees of standard mapping languages

---

## XML to Markdown Conversion

### Overview

A growing consensus in the RAG community (2024-2025) identifies **Markdown** as the superior intermediate format for ingesting structured documents (PDF, XML, DOCX) into LLMs.

### Why Markdown?

**1. Token Efficiency:**
- XML tags (`<section>`, `<paragraph>`) consume significant tokens
- Markdown denotes structure with minimal characters (`#`, `**`), reducing token usage by 20-30% compared to raw XML or HTML

**2. Semantic Understanding:**
- LLMs are heavily trained on Markdown (via GitHub code, StackOverflow, etc.)
- They inherently understand that a `# Header` implies a new topic and `* List` implies related items
- This "visual" structure aids the LLM in understanding hierarchy better than nested XML tags

**3. Chunking Friendly:**
- Markdown headers provide natural, unambiguous split points for chunking algorithms (e.g., "Split at H2")
- Whereas XML splitting requires complex DOM parsing

**Conclusion:** Converting XML to Markdown is highly effective. It acts as a "lossy compression" that retains semantic signal (hierarchy, lists, tables) while discarding syntactic noise (attributes, closing tags), making it the preferred input for vector embedding models.

### Tools and Effectiveness

| Tool | Description | Effectiveness for XML/RAG |
| :--- | :--- | :--- |
| **Docling (IBM)** | Specialized library for document parsing. Uses AI to analyze layout and converts PDF/XML/HTML to rich Markdown | **High.** Preserves tables and layout logic, which are often lost in simple regex converters. Supports hierarchical export (JSON/Markdown) specifically designed for RAG |
| **PyMuPDF4LLM** | Converts documents to Markdown with a focus on LLM readability | **Medium-High.** Excellent for standard documents; ensures clean table conversion to Markdown tables, which LLMs process well |
| **AnythingMD** | Tool focused on "AI-Ready" Markdown, stripping extraneous formatting | **High.** Focuses on semantic structure (headers, lists) to optimize retrieval accuracy |
| **Unstructured.io** | Supports partitioning documents into elements and can output Markdown | **High.** Its `hi_res` strategy uses vision models to detect layout, ensuring that the Markdown reflects the visual hierarchy, not just the DOM order |
| **MarkItDown (Microsoft)** | Open-source Python tool that converts various file formats to Markdown | **High.** Comprehensive solution with batch processing support and customizable output formatting rules |

### Workflow: XML → Markdown → RAG/Knowledge Graph

**Step 1: Convert XML to Markdown**
```python
from docling import DocumentConverter
from unstructured.io import partition_xml

# Using Docling
converter = DocumentConverter()
result = converter.convert("source.xml")
markdown_content = result.document.export_to_markdown()

# Using Unstructured.io
elements = partition_xml("source.xml", strategy="hi_res")
markdown_content = "\n\n".join([str(elem) for elem in elements])
```

**Step 2: Process Markdown for RAG**
- Markdown is easier to chunk semantically
- Headers provide natural, unambiguous split points
- Lists and tables are well-structured

**Step 3: Extract for Knowledge Graph**
- Markdown structure can guide entity extraction
- Headers often indicate entity types
- Links and references indicate relationships

---

## Best Practices and Recommendations

### General Best Practices

1. **Choose the Right Parser**
   - Use `lxml` for Python projects (recommended)
   - Use `Pygixml` for very large files requiring maximum performance
   - Use SAX for very large files
   - Use DOM for complex navigation needs

2. **Preserve Structure**
   - Maintain hierarchical relationships
   - Keep parent-child context
   - Preserve metadata and attributes
   - Implement Parent-Child indexing for RAG

3. **Handle Edge Cases**
   - Malformed XML
   - Missing attributes
   - Empty elements
   - Namespace conflicts

4. **Optimize for Scale**
   - Use streaming parsers for large files
   - Implement batch processing
   - Cache parsed results when possible

### RAG-Specific Best Practices

1. **Chunk Size**: Start with 200-400 tokens, experiment based on your data
2. **Overlap**: Use 50-100 token overlap between chunks
3. **Metadata**: Enrich chunks with XML structure information (XPath, element types)
4. **Hybrid Retrieval**: Combine vector search with metadata filtering
5. **Semantic Chunking**: Prefer semantic boundaries over fixed sizes
6. **Context Preservation**: Include parent element information
7. **Parent-Child Indexing**: Implement hierarchical retrieval for nested structures
8. **Markdown Conversion**: Convert XML to Markdown before chunking for better token efficiency

### Knowledge Graph-Specific Best Practices

1. **Schema Definition**: Define clear entity and relationship schemas
2. **Entity Disambiguation**: Implement deduplication strategies
3. **Validation**: Validate extracted data against schemas (SHACL, OWL)
4. **Incremental Updates**: Design for updating graphs as XML changes
5. **Relationship Quality**: Focus on extracting meaningful relationships
6. **Use Hybrid Approach**: Combine RML for structure with LLMs for flexibility
7. **LLM-Generated Mappings**: Use LLMs to generate RML mappings to reduce manual effort

### XML to Markdown Best Practices

1. **Preserve Structure**: Maintain headers, lists, and links
2. **Clean Output**: Remove formatting noise while keeping meaning
3. **Handle Complex Structures**: Tables, nested elements, attributes
4. **Customize Rules**: Adjust conversion rules for your XML schema
5. **Batch Processing**: Process multiple files efficiently
6. **Layout Awareness**: Use tools with layout analysis (Docling, Unstructured.io) for complex documents

---

## Tools and Libraries (2024-2025)

### Data Ingestion and Parsing

**Docling (IBM) - 2024/2025 Release**
- Comprehensive solution for parsing PDF, DOCX, and XML into structured JSON/Markdown
- Built-in support for chunking and integrates with LlamaIndex and LangChain
- Particularly noted for its ability to handle complex layouts and tables
- Supports hierarchical export specifically designed for RAG

**Unstructured.io**
- Powerhouse for ETL with "Partitioning" strategies (`auto`, `fast`, `hi_res`)
- The `xml_keep_tags` parameter allows users to toggle tag retention
- Excels at extracting metadata and standardizing diverse inputs into a common format
- `hi_res` strategy uses vision models to detect layout

**Pygixml (2025)**
- High-performance XML parser for Python, built on `pugixml` (C++)
- Outperforms `lxml` for massive XML files
- Offers XPath support and speed, crucial for preprocessing large datasets

**lxml**
- Still recommended for general-purpose XML processing
- Combines C speed with Python ease of use
- Excellent namespace handling

### RAG Frameworks

**LlamaIndex**
- Leader in structured data RAG
- **Key Components**: 
  - `HTMLNodeParser` (adaptable for XML)
  - `HierarchicalNodeParser` (implements Parent-Child indexing)
  - `AutoMergingRetriever` (merges sibling nodes into parent if enough siblings are retrieved)
- **Use Case**: Best for building the "Parent-Child" retrieval systems and handling complex document trees

**LangChain**
- Most versatile framework
- **Key Components**: 
  - `RecursiveCharacterTextSplitter`
  - `HTMLHeaderTextSplitter`
- **Use Case**: Ideal for pipelines requiring complex flows, agentic behaviors, and "Markdown-first" strategies

### Knowledge Graph Construction

**Neo4j LLM Knowledge Graph Builder (2025)**
- Automates the extraction of entities and relationships from unstructured text/XML using LLMs
- Features for "Community Summarization" (GraphRAG)
- Integrates with LangChain's GraphTransformer

**RMLMapper / CARML**
- Essential for the deterministic "Hybrid" pipelines where RML handles the structural mapping of XML to RDF
- Improved support for complex XML namespaces and functions (FnO)

**Morph-KGC**
- R2RML, RML, and RML-star processor to generate RDF and RDF-star knowledge graphs from heterogeneous data sources at scale

### Vector Databases

**Weaviate / Pinecone / Milvus**
- Evolved to support "Multi-Tenancy" and rich metadata filtering
- In 2025, optimized for "Hybrid Search" (Sparse + Dense vectors)
- Critical when combining XML metadata filters with semantic text search

### Markdown Conversion Tools

**MarkItDown (Microsoft)**
- Open-source Python tool
- Converts various file formats (PDF, Word, PowerPoint, images, XML) to Markdown
- Batch processing support
- Customizable output formatting rules

**AnythingMD**
- Focuses on "AI-Ready" Markdown
- Strips extraneous formatting
- Optimizes for semantic structure

---

## Implementation Examples

### Complete Example: XML → Markdown → RAG Pipeline with Parent-Child Indexing

```python
from docling import DocumentConverter
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.node_parser import HierarchicalNodeParser
from llama_index.core.retrievers import AutoMergingRetriever
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

class XMLRAGPipeline:
    def __init__(self, vector_db_path: str = "./chroma_db"):
        # Initialize Docling converter
        self.converter = DocumentConverter()
        
        # Initialize vector store
        chroma_client = chromadb.PersistentClient(path=vector_db_path)
        chroma_collection = chroma_client.get_or_create_collection("xml_documents")
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        # Create hierarchical node parser (Parent-Child indexing)
        self.node_parser = HierarchicalNodeParser.from_defaults(
            chunk_sizes=[2048, 512, 128]  # Parent, child, grandchild
        )
        
        # Create index
        self.index = VectorStoreIndex(
            nodes=[],
            storage_context=storage_context
        )
        
        # Create auto-merging retriever
        self.retriever = AutoMergingRetriever(
            self.index.as_retriever(similarity_top_k=6),
            storage_context=storage_context,
            verbose=True
        )
    
    def process_xml(self, xml_file: str):
        """Convert XML to Markdown and create hierarchical nodes"""
        # Step 1: Convert XML to Markdown using Docling
        result = self.converter.convert(xml_file)
        markdown_content = result.document.export_to_markdown()
        
        # Step 2: Create hierarchical nodes
        nodes = self.node_parser.get_nodes_from_documents([markdown_content])
        
        # Step 3: Add nodes to index
        self.index.insert_nodes(nodes)
        
        return nodes
    
    def query(self, query_text: str, n_results: int = 5):
        """Query with automatic parent merging"""
        results = self.retriever.retrieve(query_text)
        return results[:n_results]

# Usage
pipeline = XMLRAGPipeline()
pipeline.process_xml("documents.xml")
results = pipeline.query("What is machine learning?")
```

### Complete Example: XML → Knowledge Graph with Hybrid Approach

```python
from lxml import etree
from neo4j import GraphDatabase
from langchain_community.graphs import Neo4jGraph
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_openai import ChatOpenAI

class XMLToKnowledgeGraphHybrid:
    def __init__(self, uri: str, user: str, password: str, llm_api_key: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.graph = Neo4jGraph(url=uri, username=user, password=password)
        
        # Initialize LLM for hybrid extraction
        llm = ChatOpenAI(temperature=0, model="gpt-4", api_key=llm_api_key)
        self.llm_transformer = LLMGraphTransformer(llm=llm)
    
    def close(self):
        self.driver.close()
    
    def extract_with_llm(self, xml_file: str):
        """Extract entities and relationships using LLM"""
        tree = etree.parse(xml_file)
        
        # Extract text content from XML
        text_content = []
        for element in tree.xpath("//article | //section"):
            text = element.text.strip() if element.text else ""
            if text:
                text_content.append(text)
        
        # Use LLM to extract graph structure
        combined_text = "\n\n".join(text_content)
        graph_documents = self.llm_transformer.convert_to_graph_documents([combined_text])
        
        return graph_documents
    
    def create_graph(self, graph_documents):
        """Create knowledge graph in Neo4j"""
        self.graph.add_graph_documents(graph_documents)
    
    def extract_structured(self, xml_file: str):
        """Extract structured relationships from XML hierarchy"""
        tree = etree.parse(xml_file)
        relationships = []
        
        # Extract article-author relationships
        for article in tree.xpath("//article"):
            article_id = article.get("id")
            for author in article.xpath(".//author"):
                author_id = author.get("id")
                relationships.append({
                    "source": article_id,
                    "target": author_id,
                    "type": "AUTHORED_BY"
                })
        
        return relationships
    
    def create_structured_relationships(self, relationships: list):
        """Create structured relationships in Neo4j"""
        with self.driver.session() as session:
            for rel in relationships:
                query = """
                MATCH (a), (b)
                WHERE a.id = $source AND b.id = $target
                MERGE (a)-[r:AUTHORED_BY]->(b)
                """
                session.run(query, source=rel["source"], target=rel["target"])

# Usage
kg = XMLToKnowledgeGraphHybrid(
    "bolt://localhost:7687", 
    "neo4j", 
    "password",
    "your-openai-api-key"
)

# Hybrid approach: LLM extraction + structured extraction
graph_docs = kg.extract_with_llm("documents.xml")
kg.create_graph(graph_docs)

structured_rels = kg.extract_structured("documents.xml")
kg.create_structured_relationships(structured_rels)

kg.close()
```

---

## Conclusion

For 2025, the optimal pipeline for XML RAG involves:

1. **Parsing XML** with Docling or Unstructured.io
2. **Converting to Markdown** to strip syntactic noise
3. **Applying Hierarchical Chunking** with **Parent-Child indexing**
4. **Using Hybrid Retrieval** (vector search + metadata filtering)

For Knowledge Graphs, a **Hybrid approach** utilizing:
- LLMs to generate or enhance RML mappings
- RML for deterministic structural mapping
- LLM extraction for unstructured text fields

The era of treating XML as simple text is over; structure-aware processing is now the baseline for high-performance AI systems.

---

## References

### Deep Research Sources
- Gemini Deep Research Analysis (December 2025)
- Comprehensive analysis of XML processing strategies for RAG and Knowledge Graphs
- Multi-hop reasoning across research papers, documentation, and industry best practices

### Key Tools
- [Docling (IBM)](https://github.com/IBM/docling)
- [Unstructured.io](https://unstructured.io/)
- [MarkItDown (Microsoft)](https://github.com/microsoft/markitdown)
- [LlamaIndex](https://www.llamaindex.ai/)
- [Neo4j LLM Knowledge Graph Builder](https://neo4j.com/developer-blog/generating-knowledge-graphs-with-llms/)
- [RMLMapper](https://github.com/RMLio/rmlmapper-java)

---

*Document generated: December 2025*
*Enhanced with Deep Research Analysis*
