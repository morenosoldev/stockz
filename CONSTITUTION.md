# Recover-Bot Project Constitution

## Core Principles

### 1. Facts-First Data
- **Attribution Required**: All market data, news, and social sentiment must be attributed to their sources
- **No Data Invention**: LLMs are used only for summarization and classification, never to generate or invent data
- **Traceability**: Every data point must be traceable to its original source

### 2. Reproducibility
- **Versioned Data Snapshots**: Every daily run uses versioned, immutable data snapshots
- **Feature Versioning**: All feature engineering logic is versioned
- **Model Versioning**: Scoring models and configurations are versioned
- **Deterministic Results**: Given the same inputs and versions, outputs must be identical

### 3. Safety
- **No Order Placement in V1**: Read-only mode - no actual trading capabilities
- **Shadow Mode Evaluation**: All signals evaluated in simulation only
- **Human Oversight**: Manual verification required for system changes

### 4. Observability
- **Structured Logging**: All events logged in structured format with consistent schemas
- **Key Metrics**: Track job runtime, error rates, number of candidates processed, average scores
- **Monitoring**: Real-time visibility into system performance and bottlenecks
- **Error Tracking**: Comprehensive error categorization and alerting

### 5. Modularity
- **Pluggable Strategies**: Self-contained, swappable strategy modules
- **Strategy Folders**: Each strategy contains:
  - Feature engineering code
  - Scoring logic
  - Configuration files
  - Evaluation hooks
  - Documentation
- **Clean Interfaces**: Well-defined APIs between components

### 6. Performance
- **Universe Size**: Designed to scan 1,000-2,000 tickers
- **Time Constraints**: Complete daily scans within N minutes (target: <30 min)
- **Cached Data**: Leverage caching to minimize API calls and latency
- **Concurrency**: Parallel processing where safe

### 7. Simplicity First
- **MVP = Rules-Based**: Start with rules-based scoring systems
- **ML as Enhancement**: Machine learning is a later swap-in, not a requirement
- **Clear Code**: Prioritize readability and maintainability
- **Minimal Dependencies**: Only necessary external libraries
- **Incremental Complexity**: Add sophistication only after core is stable

## Success Criteria

- **Reliability**: 99%+ successful daily runs
- **Performance**: Scans complete within time constraints  
- **Data Quality**: <1% data errors or missing attributions
- **Reproducibility**: 100% reproducible results given same inputs

---

**Next Steps**: Define technology stack, implementation architecture, and development roadmap.
