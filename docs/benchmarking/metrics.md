# Benchmarking Metrics Reference

Comprehensive definitions and interpretations of all metrics used in Dolphin benchmarking.

## Table of Contents

- [Performance Metrics](#performance-metrics)
  - [Latency Metrics](#latency-metrics)
  - [Throughput Metrics](#throughput-metrics)
  - [Resource Metrics](#resource-metrics)
- [Quality Metrics](#quality-metrics)
  - [Ranking Metrics](#ranking-metrics)
  - [Retrieval Metrics](#retrieval-metrics)
- [ANN-Specific Metrics](#ann-specific-metrics)
- [Composite Metrics](#composite-metrics)
- [Interpretation Guidelines](#interpretation-guidelines)

---

## Performance Metrics

### Latency Metrics

Latency measures how long operations take. We track percentiles to understand the full distribution.

#### **p50 (Median) Latency**

**Definition**: The 50th percentile latency - half of requests complete faster, half slower.

**Formula**:
```
Sort all latencies L[1..n]
p50 = L[n/2]
```

**Target**: < 50ms for typical queries

**Interpretation**:
- **< 50ms**: Excellent - feels instant to users
- **50-100ms**: Good - responsive
- **100-200ms**: Acceptable - noticeable but usable
- **> 200ms**: Poor - users perceive as slow

**Example**:
```python
latencies = [23, 31, 42, 55, 67, 89, 120]  # ms
p50 = 55  # The median value
```

#### **p95 Latency**

**Definition**: The 95th percentile latency - 95% of requests complete faster than this.

**Formula**:
```
Sort all latencies L[1..n]
p95 = L[int(n * 0.95)]
```

**Target**: < 150ms

**Interpretation**:
- Captures "typical bad case" - occasional slow requests
- More sensitive to outliers than p50
- Critical for user experience consistency

**Why it matters**: If p95 is 500ms, 1 in 20 requests is painfully slow even if median is fast.

#### **p99 Latency**

**Definition**: The 99th percentile latency - 99% of requests complete faster than this.

**Formula**:
```
Sort all latencies L[1..n]
p99 = L[int(n * 0.99)]
```

**Target**: < 300ms

**Interpretation**:
- Captures "rare but real" worst-case scenarios
- Important for reliability and tail latency
- Often affected by GC, I/O spikes, or resource contention

**Trade-offs**: Optimizing p99 can be expensive - focus on p95 first.

#### **Mean Latency**

**Definition**: Average latency across all measurements.

**Formula**:
```
mean = sum(latencies) / len(latencies)
```

**Caution**: Can be misleading due to outliers. Prefer percentiles.

**Use case**: Useful for overall system capacity planning.

#### **Standard Deviation**

**Definition**: Measure of latency variability.

**Formula**:
```
stddev = sqrt(sum((x - mean)^2) / n)
```

**Interpretation**:
- **Low stddev**: Predictable performance (good)
- **High stddev**: Inconsistent performance (investigate)

---

### Throughput Metrics

#### **Queries Per Second (QPS)**

**Definition**: Number of queries the system can handle per second.

**Measurement**:
```python
queries_completed = 1000
elapsed_seconds = 10.5
qps = queries_completed / elapsed_seconds  # 95.2 QPS
```

**Target**: > 100 QPS (single-threaded), > 1000 QPS (concurrent)

**Scaling factors**:
- Linear with cores (for independent queries)
- Limited by I/O, embeddings API, or DB contention

#### **Throughput Under Load**

**Definition**: Sustained QPS with realistic concurrency.

**Measurement approach**:
```python
# Simulate 10 concurrent users
concurrent_workers = 10
duration = 60  # seconds
total_queries = measure_throughput(workers=10, duration=60)
qps = total_queries / duration
```

**Targets**:
- **10 concurrent users**: > 500 QPS
- **50 concurrent users**: > 1000 QPS
- **100 concurrent users**: > 1500 QPS

---

### Resource Metrics

#### **Memory Usage**

**Peak memory**: Max RSS during benchmark run

**Measurement**:
```python
import resource
peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
```

**Targets**:
- **Index 10K files**: < 2GB peak
- **Index 100K files**: < 8GB peak
- **Query (no reranking)**: < 100MB incremental

#### **CPU Utilization**

**Average CPU %** during sustained load.

**Interpretation**:
- **< 50%**: Under-utilized (can handle more load)
- **50-80%**: Healthy utilization
- **> 90%**: Saturated (need scaling)

#### **Disk I/O**

**Read IOPS** and **bandwidth** during indexing/queries.

**Monitoring**: Track via `iostat` or system metrics.

---

## Quality Metrics

Quality metrics measure how well the system retrieves relevant results.

### Ranking Metrics

#### **Mean Reciprocal Rank (MRR)**

**Definition**: Average of the reciprocal rank of the first relevant result.

**Formula**:
```
For each query i:
  rank_i = position of first relevant result (1-indexed)
  RR_i = 1 / rank_i

MRR = (1/N) * sum(RR_i) for all N queries
```

**Range**: 0.0 to 1.0

**Target**: > 0.85

**Interpretation**:
- **MRR = 1.0**: Perfect - first result always relevant
- **MRR = 0.5**: First relevant result at position 2 (average)
- **MRR = 0.33**: First relevant result at position 3 (average)
- **MRR = 0.1**: First relevant result at position 10 (average)

**Example**:
```python
# Query 1: First relevant result at position 1 -> RR = 1.0
# Query 2: First relevant result at position 2 -> RR = 0.5
# Query 3: First relevant result at position 1 -> RR = 1.0
# Query 4: First relevant result at position 5 -> RR = 0.2

MRR = (1.0 + 0.5 + 1.0 + 0.2) / 4 = 0.675
```

**Use case**: Best for scenarios where users care most about the top result (e.g., "jump to definition").

#### **Mean Average Precision (MAP)**

**Definition**: Mean of average precision scores across queries.

**Formula**:
```
For query i with R relevant results:
  Precision@k = (relevant results in top k) / k
  AP_i = (1/R) * sum(Precision@k * rel(k)) for all k

MAP = (1/N) * sum(AP_i) for all N queries
```

**Range**: 0.0 to 1.0

**Target**: > 0.80

**Interpretation**: Rewards ranking all relevant results highly, not just the first.

**Example**:
```python
# Query: Relevant results at positions 1, 3, 5 (out of 10)
# P@1 = 1/1 = 1.0 (relevant)
# P@2 = 1/2 = 0.5 (not relevant)
# P@3 = 2/3 = 0.67 (relevant)
# P@5 = 3/5 = 0.6 (relevant)

AP = (1/3) * (1.0 + 0.67 + 0.6) = 0.757
```

**Use case**: Best when users explore multiple results (e.g., "find all usages").

---

### Retrieval Metrics

#### **Precision@K (P@K)**

**Definition**: Fraction of top-K results that are relevant.

**Formula**:
```
P@K = (# relevant results in top K) / K
```

**Range**: 0.0 to 1.0

**Common values**:
- **P@5**: Precision at 5 results (target: > 0.80)
- **P@10**: Precision at 10 results (target: > 0.70)

**Interpretation**:
- **P@5 = 1.0**: All top 5 results are relevant (perfect)
- **P@5 = 0.6**: 3 out of 5 results are relevant (acceptable)
- **P@5 = 0.2**: Only 1 out of 5 relevant (poor)

**Example**:
```python
top_10_results = ["relevant", "relevant", "not relevant", "relevant",
                  "not relevant", "not relevant", "relevant",
                  "relevant", "not relevant", "relevant"]

relevant_count = 6
P@10 = 6 / 10 = 0.60
```

**Trade-off**: High precision may sacrifice recall.

#### **Recall@K (R@K)**

**Definition**: Fraction of all relevant results found in top-K.

**Formula**:
```
R@K = (# relevant results in top K) / (total # relevant results)
```

**Range**: 0.0 to 1.0

**Common values**:
- **R@10**: Recall at 10 results (target: > 0.90)
- **R@20**: Recall at 20 results (target: > 0.95)

**Interpretation**:
- **R@10 = 1.0**: Found all relevant results in top 10 (perfect)
- **R@10 = 0.9**: Found 90% of relevant results (excellent)
- **R@10 = 0.5**: Missed half of relevant results (poor)

**Example**:
```python
total_relevant_in_corpus = 10
found_in_top_10 = 9

R@10 = 9 / 10 = 0.90
```

**Trade-off**: High recall may sacrifice precision.

#### **F1@K Score**

**Definition**: Harmonic mean of Precision@K and Recall@K.

**Formula**:
```
F1@K = 2 * (P@K * R@K) / (P@K + R@K)
```

**Range**: 0.0 to 1.0

**Use case**: Balanced metric when both precision and recall matter equally.

**Example**:
```python
P@10 = 0.7  # 7 out of 10 results relevant
R@10 = 0.7  # Found 7 out of 10 total relevant

F1@10 = 2 * (0.7 * 0.7) / (0.7 + 0.7) = 0.70
```

---

## ANN-Specific Metrics

Metrics specific to Approximate Nearest Neighbor (ANN) search.

### **Recall (vs. Exhaustive Search)**

**Definition**: Fraction of true nearest neighbors found by ANN.

**Measurement**:
```python
# Ground truth: exact k-NN using exhaustive search
exact_results = exhaustive_search(query, k=10)
exact_ids = {r.id for r in exact_results}

# ANN results
ann_results = ann_search(query, k=10)
ann_ids = {r.id for r in ann_results}

recall = len(exact_ids & ann_ids) / len(exact_ids)
```

**Target**: > 0.95 (find 95%+ of true nearest neighbors)

**Trade-off**: Higher recall requires more probes (slower, more expensive).

### **Speedup Factor**

**Definition**: How much faster ANN is compared to exhaustive search.

**Formula**:
```
speedup = latency_exhaustive / latency_ann
```

**Example**:
```python
exhaustive_time = 200  # ms
ann_time = 20  # ms
speedup = 200 / 20 = 10x
```

**Interpretation**:
- **10x**: Good speedup for modest datasets
- **100x**: Excellent speedup for large datasets
- **< 2x**: ANN overhead may not be worth it

### **Efficiency Frontier**

**Definition**: Plot of recall vs. latency for different ANN configurations.

**Use case**: Find optimal balance between speed and accuracy.

**Example configurations**:
```python
# Fast but less accurate
nprobes=5, refine_factor=3  -> 15ms, 0.90 recall

# Balanced
nprobes=10, refine_factor=5  -> 30ms, 0.95 recall

# Accurate but slower
nprobes=20, refine_factor=10  -> 80ms, 0.99 recall
```

**Goal**: Operate at the "knee" of the curve - best recall/latency trade-off.

---

## Composite Metrics

### **Quality-Adjusted Throughput**

**Definition**: QPS weighted by retrieval quality.

**Formula**:
```
QAT = QPS * MRR
```

**Use case**: Compare configurations that trade throughput for quality.

**Example**:
```python
# Config A: Fast but lower quality
QPS_A = 200, MRR_A = 0.70  -> QAT = 140

# Config B: Slower but higher quality
QPS_B = 150, MRR_B = 0.90  -> QAT = 135

# Config A is better (higher QAT)
```

### **Cost per Query**

**Definition**: Embedding API cost + compute cost per query.

**Formula**:
```
cost_per_query = (embedding_tokens * cost_per_token) + (cpu_seconds * cost_per_cpu_second)
```

**Use case**: Optimize for cost efficiency.

---

## Interpretation Guidelines

### Setting Targets

**Start with baselines**:
1. Measure current performance
2. Set targets 10-20% better than baseline
3. Iterate as system improves

**Industry benchmarks** (for reference):
- **Elasticsearch**: p50 < 10ms, p95 < 100ms
- **Pinecone**: p50 < 50ms, p95 < 200ms
- **Traditional DBs**: p50 < 5ms, p95 < 50ms

### Acceptable Trade-offs

| Scenario | Prioritize | Acceptable Trade-off |
|----------|------------|---------------------|
| Interactive search | p50, p95 latency | Slightly lower recall |
| Batch processing | Throughput | Higher latency |
| Accuracy-critical | MRR, P@K | Lower throughput |
| Cost-sensitive | Cost per query | Slightly lower quality |

### Red Flags

**Performance red flags**:
- p95 > 3x p50 (high variance)
- p99 > 10x p50 (extreme outliers)
- QPS degradation under load

**Quality red flags**:
- MRR < 0.70 (poor ranking)
- P@5 < 0.60 (too many irrelevant results)
- R@10 < 0.80 (missing relevant results)

### Debugging Metrics

When metrics regress:

1. **High latency**:
   - Check ANN parameters (nprobes, refine_factor)
   - Profile query execution
   - Look for resource contention

2. **Low recall**:
   - Verify index is built correctly
   - Check ANN configuration
   - Ensure vectors are normalized

3. **Low MRR/Precision**:
   - Review ranking algorithm
   - Check reranking configuration
   - Analyze failed queries in golden scenarios

4. **Low throughput**:
   - Check for bottlenecks (embeddings API, DB, CPU)
   - Verify connection pooling
   - Look for serialization points

---

## Statistical Significance

### Sample Size

**Minimum samples** for reliable metrics:
- **Latency percentiles**: 100+ measurements
- **MRR/MAP**: 50+ queries
- **P@K/R@K**: 30+ queries per category

### Confidence Intervals

Report metrics with confidence intervals:
```python
import scipy.stats as stats

# 95% confidence interval for mean latency
mean = np.mean(latencies)
sem = stats.sem(latencies)
ci = stats.t.interval(0.95, len(latencies)-1, mean, sem)

print(f"Mean: {mean:.1f}ms (95% CI: {ci[0]:.1f}-{ci[1]:.1f})")
```

### Statistical Tests

When comparing configurations:
- **Latency**: Mann-Whitney U test (non-parametric)
- **MRR/MAP**: Paired t-test (if normally distributed)
- **Significance threshold**: p < 0.05

---

## References

- [Information Retrieval Evaluation](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html)
- [FAISS Benchmark Methodology](https://github.com/facebookresearch/faiss/wiki/Indexing-1M-vectors)
- [Latency Percentiles](https://www.elastic.co/blog/averages-can-dangerous-use-percentile)
- [Statistical Significance in A/B Testing](https://www.evanmiller.org/ab-testing/sample-size.html)

---

## Summary

| Metric | What it measures | Target | Use case |
|--------|------------------|--------|----------|
| **p50 latency** | Typical query speed | < 50ms | User experience |
| **p95 latency** | Consistency | < 150ms | Reliability |
| **QPS** | System capacity | > 100 | Scalability |
| **MRR** | Ranking quality | > 0.85 | Single best result |
| **P@K** | Precision | > 0.70 | Result quality |
| **R@K** | Completeness | > 0.90 | Coverage |
| **ANN Recall** | Accuracy vs. exact | > 0.95 | ANN tuning |
| **Speedup** | Performance gain | > 10x | ANN validation |

Choose metrics based on your use case and optimize accordingly.
