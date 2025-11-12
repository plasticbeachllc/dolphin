# Benchmarking Best Practices

Proven guidelines and recommendations for reliable, actionable benchmarking.

## Table of Contents

- [General Principles](#general-principles)
- [Measurement Practices](#measurement-practices)
- [Statistical Rigor](#statistical-rigor)
- [Environment Control](#environment-control)
- [Result Interpretation](#result-interpretation)
- [Optimization Workflow](#optimization-workflow)
- [Common Pitfalls](#common-pitfalls)
- [Troubleshooting](#troubleshooting)

---

## General Principles

### 1. Measure First, Optimize Second

**Don't**:
```python
# Premature optimization
def search(query):
    # Let me optimize this before measuring...
    query = query.lower().strip()  # Is this even a bottleneck?
```

**Do**:
```python
# Measure first
results = benchmark_search()  # Baseline: 50ms
# Profile to find bottleneck: ANN search takes 35ms (70% of time)
# Then optimize ANN parameters
```

**Rationale**:
- Intuition about performance is often wrong
- Optimize the biggest bottlenecks first (80/20 rule)
- Measurement prevents wasted effort

### 2. Establish Baselines

**Always establish a baseline before making changes**:

```bash
# Before optimization
just benchmark-full > baseline_before.txt
cp results/benchmark.json baseline/before_optimization.json

# Make changes...

# After optimization
just benchmark-full > baseline_after.txt
python scripts/compare_benchmarks.py \
  baseline/before_optimization.json \
  results/benchmark.json
```

**Why**:
- Quantify improvement objectively
- Catch regressions immediately
- Validate optimization hypotheses

### 3. Make Changes Incrementally

**Don't**:
```bash
# Change everything at once
- Update ANN parameters
- Change reranking algorithm
- Modify chunking
- Update embedding model

# Now which change caused the improvement?
```

**Do**:
```bash
# Change one thing at a time
1. Baseline: nprobes=10, refine_factor=5 -> 50ms, MRR 0.87
2. Test: nprobes=15, refine_factor=5 -> 65ms, MRR 0.89
3. Test: nprobes=10, refine_factor=8 -> 58ms, MRR 0.88
4. Choose: nprobes=10, refine_factor=8 (best balance)
```

**Why**:
- Isolate cause and effect
- Understand what actually helps
- Avoid accidental regressions

### 4. Consider Trade-offs

**Performance vs Quality**:
```
Configuration     Latency    MRR    Trade-off
────────────────────────────────────────────────
Fast              20ms      0.82    -8% quality for 2.5x speed
Default           50ms      0.87    Balanced
Accurate          100ms     0.91    +5% quality for 2x latency
```

**When to choose what**:
- **Fast**: High QPS, search-as-you-type, preview
- **Default**: General use, good balance
- **Accurate**: Critical queries, final results

**Key question**: What is the user impact of this trade-off?

---

## Measurement Practices

### 1. Sufficient Sample Size

**Latency measurements**:
```python
# Too few samples - unreliable
latencies = [run_query() for _ in range(10)]  # ❌

# Sufficient samples - reliable percentiles
latencies = [run_query() for _ in range(100)]  # ✓
```

**Minimum recommendations**:
- Latency percentiles: 100+ measurements
- MRR/MAP: 50+ queries
- Per-category metrics: 30+ queries

**Why**: Small samples have high variance and unreliable percentiles.

### 2. Warm-up Runs

**Cold start vs. warmed up**:
```python
# Incorrect - includes cold start
results = [benchmark_query() for _ in range(100)]

# Correct - warm up first
for _ in range(10):
    benchmark_query()  # Warm-up runs
results = [benchmark_query() for _ in range(100)]  # Actual measurements
```

**What to warm up**:
- JIT compilation
- Disk caches
- Connection pools
- Vector index loading

### 3. Multiple Iterations

**Per-query iteration**:
```python
# Measure each query multiple times
for query in test_queries:
    latencies = []
    for _ in range(iterations):  # e.g., 10 iterations
        start = time.time()
        result = search(query)
        latencies.append(time.time() - start)

    # Compute stats for this query
    median_latency = statistics.median(latencies)
```

**Why**: Reduces noise from transient effects.

### 4. Randomization

**Query order**:
```python
# Don't test in predictable order
queries = load_queries()
random.shuffle(queries)  # Randomize order

for query in queries:
    benchmark(query)
```

**Why**: Avoid systematic biases (caching effects, memory growth, etc.).

---

## Statistical Rigor

### 1. Report Percentiles, Not Just Means

**Don't**:
```python
mean_latency = sum(latencies) / len(latencies)
print(f"Average: {mean_latency}ms")  # ❌ Hides outliers
```

**Do**:
```python
latencies.sort()
p50 = latencies[len(latencies) // 2]
p95 = latencies[int(len(latencies) * 0.95)]
p99 = latencies[int(len(latencies) * 0.99)]

print(f"p50: {p50}ms, p95: {p95}ms, p99: {p99}ms")  # ✓
```

**Why**: Means are misleading with outliers. Percentiles show the full distribution.

### 2. Statistical Significance

**Is the difference real?**
```python
from scipy import stats

# Mann-Whitney U test (non-parametric)
statistic, p_value = stats.mannwhitneyu(baseline_latencies, current_latencies)

if p_value < 0.05:
    print("Difference is statistically significant")
else:
    print("Difference could be random noise")
```

**When to use**:
- Comparing configurations
- Validating optimizations
- Regression detection

### 3. Confidence Intervals

**Report uncertainty**:
```python
import scipy.stats as stats

mean = np.mean(latencies)
sem = stats.sem(latencies)
ci = stats.t.interval(0.95, len(latencies)-1, mean, sem)

print(f"Mean: {mean:.1f}ms (95% CI: {ci[0]:.1f}-{ci[1]:.1f})")
```

**Interpretation**:
- Narrow CI (e.g., 50±2ms): High confidence
- Wide CI (e.g., 50±15ms): High variance, need more samples

### 4. Regression Thresholds

**Set appropriate thresholds**:
```python
# Too strict - false positives from noise
threshold = 1%  # ❌ Natural variance may trigger this

# Too loose - miss real regressions
threshold = 50%  # ❌ Huge regressions slip through

# Reasonable
threshold = 5-10%  # ✓ Balance between sensitivity and noise
```

**Guidelines**:
- **5%**: Strict (for stable metrics)
- **10%**: Standard (general use)
- **15%**: Lenient (for noisy metrics)

---

## Environment Control

### 1. Isolate Benchmarks

**Don't**:
```bash
# Running while system is busy
just benchmark-full  # While IDE, browser, Slack are open
```

**Do**:
```bash
# Minimize interference
# Close unnecessary apps
# Run on dedicated machine or CI
just benchmark-full
```

**Why**: Background processes add noise and unpredictable latency.

### 2. Consistent Hardware

**Document environment**:
```json
{
  "environment": {
    "os": "Ubuntu 22.04",
    "cpu": "Intel i7-10700K @ 3.80GHz (8 cores)",
    "memory": "32GB DDR4",
    "disk": "Samsung 970 EVO NVMe SSD",
    "python": "3.11.5"
  }
}
```

**Why**: Performance varies dramatically across hardware. Document for reproducibility.

### 3. Fixed Random Seeds

**Reproducible randomness**:
```python
import random
import numpy as np

# Fix seeds
random.seed(42)
np.random.seed(42)

# Now tests are reproducible
queries = generate_random_queries(n=100)
```

**Why**: Eliminates variance from random query generation.

### 4. Temperature and Throttling

**Check for thermal throttling**:
```bash
# Monitor CPU temperature during benchmark
watch -n 1 sensors

# If CPU throttles (>80°C):
# - Improve cooling
# - Reduce load
# - Run shorter benchmarks
```

**Why**: Thermal throttling silently degrades performance.

---

## Result Interpretation

### 1. Look at Distributions, Not Just Metrics

**Don't just trust summary stats**:
```python
# Summary: p50=50ms looks good
# But p99=5000ms reveals a problem!
```

**Visualize distributions**:
```python
import matplotlib.pyplot as plt

plt.hist(latencies, bins=50)
plt.xlabel('Latency (ms)')
plt.ylabel('Frequency')
plt.title('Latency Distribution')
plt.show()
```

**Look for**:
- Bimodal distributions (two performance modes)
- Long tails (rare but severe outliers)
- Spikes (systematic issues)

### 2. Correlation vs. Causation

**Be careful with conclusions**:
```
Observation: Latency improved after updating dependency X
Conclusion: Updating X improved latency

But: Did we also change something else?
     Was it random variance?
     Is it reproducible?
```

**Validate**:
- Reproduce the result multiple times
- Test the specific hypothesis (A/B test)
- Look for confounding factors

### 3. Context Matters

**Absolute vs. Relative**:
```
p50: 5ms → 10ms (100% regression!) 😱
But: Still well under 50ms target ✓

p50: 200ms → 250ms (25% regression)
And: Exceeds 50ms target ❌ This is serious!
```

**Consider**:
- Target thresholds
- User perception (JND: Just Noticeable Difference)
- Business impact

### 4. Variance and Noise

**Is it a real change?**
```
Run 1: 50ms
Run 2: 52ms
Run 3: 48ms
Run 4: 51ms

Variance: ±4% is normal noise, not a regression
```

**Natural variance sources**:
- System load fluctuations
- GC pauses
- Network variability
- Disk I/O contention

**Rule of thumb**: Changes < 10% may be noise unless statistically validated.

---

## Optimization Workflow

### Step-by-Step Process

```
1. Measure baseline
   ├─ Run full benchmarks
   ├─ Record all metrics
   └─ Document environment

2. Profile to find bottlenecks
   ├─ Identify slow components
   ├─ Quantify each contribution
   └─ Prioritize by impact

3. Hypothesize optimization
   ├─ What will this change?
   ├─ What's the expected improvement?
   └─ What are the risks/trade-offs?

4. Implement change
   ├─ Change one thing
   └─ Keep change isolated

5. Measure impact
   ├─ Run benchmarks again
   ├─ Compare to baseline
   └─ Check for regressions

6. Validate
   ├─ Statistical significance?
   ├─ Reproducible?
   └─ Trade-offs acceptable?

7. Document or revert
   ├─ If good: commit, update baseline
   └─ If bad: revert, try different approach
```

### Example: Optimizing ANN Parameters

```bash
# 1. Baseline
python scripts/benchmark_ann.py --nprobes 10 --refine-factor 5
# Result: 50ms p50, 0.87 MRR

# 2. Profile
# Finding: ANN search takes 70% of time (35ms)

# 3. Hypothesis: Reduce nprobes to speed up search
# Expected: -30% latency, -3% MRR

# 4. Test
python scripts/benchmark_ann.py --nprobes 7 --refine-factor 5
# Result: 38ms p50 (-24%), 0.85 MRR (-2.3%)

# 5. Validate: Trade-off acceptable?
# Decision: Yes, -2.3% quality for +32% speed is good for fast config

# 6. Document
git commit -m "Add fast ANN config: nprobes=7 (-24% latency, -2.3% MRR)"
```

---

## Common Pitfalls

### 1. Optimizing the Wrong Thing

**Pitfall**: Spend time optimizing something that doesn't matter.
```python
# Optimize JSON serialization (saves 1ms)
# When ANN search takes 50ms (98% of time)
```

**Solution**: Profile first, optimize the biggest bottlenecks.

### 2. Ignoring Regressions

**Pitfall**: "It's probably fine" attitude towards regressions.
```bash
# p95 increased from 100ms to 150ms
# "It's only 50ms, no big deal"
# But: 50% regression affects user experience!
```

**Solution**: Investigate all regressions. Small ones accumulate.

### 3. Testing in Unrealistic Conditions

**Pitfall**: Benchmark with empty index or simple queries.
```python
# Test with 10 files
benchmark()  # Fast!

# Production: 100,000 files
# Reality: 10x slower
```

**Solution**: Test with realistic data volumes and query complexity.

### 4. Comparing Apples to Oranges

**Pitfall**: Inconsistent benchmark conditions.
```bash
# Baseline: Cold start, small index
# Current: Warm cache, large index
# Comparison is meaningless!
```

**Solution**: Control all variables except the one you're testing.

### 5. Overfitting to Benchmarks

**Pitfall**: Optimize for specific test queries, not general performance.
```python
# Special case the exact queries in golden scenarios
if query == "LanceDBStore class":
    return cached_result  # Cheating!
```

**Solution**: Test on diverse, realistic queries. Update scenarios regularly.

### 6. Not Documenting Trade-offs

**Pitfall**: Focus only on improved metrics, ignore regressions.
```markdown
# PR description: "Improved p50 by 20%!"
# (But p99 regressed by 50% - not mentioned)
```

**Solution**: Always document trade-offs transparently.

---

## Troubleshooting

### High Variance

**Symptoms**: Results vary wildly between runs.

**Causes**:
- Insufficient sample size
- Background processes
- Thermal throttling
- Random data generation without fixed seed

**Solutions**:
- Increase sample size (100+ measurements)
- Close background apps
- Fix random seeds
- Run on dedicated hardware

### Inconsistent Results

**Symptoms**: Can't reproduce previous benchmarks.

**Causes**:
- Different data
- Different environment
- Cache effects
- Non-deterministic code

**Solutions**:
- Version control test data
- Document environment completely
- Warm up caches consistently
- Use fixed random seeds

### Unexpected Regressions

**Symptoms**: Performance degraded but code looks fine.

**Causes**:
- Unintended side effects
- Dependency updates
- Configuration changes
- Data changes

**Solutions**:
- Git bisect to find culprit commit
- Check dependency versions
- Compare configurations
- Verify test data hasn't changed

### Noisy Metrics

**Symptoms**: Results fluctuate ±20% randomly.

**Causes**:
- Shared development machine
- Network latency (external APIs)
- GC pauses
- I/O contention

**Solutions**:
- Run on CI with dedicated resources
- Mock external APIs for benchmarks
- Tune GC settings
- Use faster storage (SSD)

---

## Checklist

### Before Benchmarking
- [ ] Close unnecessary applications
- [ ] Ensure system is cool (not thermal throttling)
- [ ] Verify test data is ready
- [ ] Check git status (clean state)
- [ ] Document environment

### During Benchmarking
- [ ] Run warm-up iterations
- [ ] Use sufficient sample sizes
- [ ] Randomize query order
- [ ] Monitor resource usage
- [ ] Save raw results

### After Benchmarking
- [ ] Compute percentiles (p50, p95, p99)
- [ ] Compare to baseline
- [ ] Check statistical significance
- [ ] Document findings
- [ ] Commit results to version control

### Before Merging
- [ ] All benchmarks pass
- [ ] No regressions > threshold
- [ ] Trade-offs documented
- [ ] Golden scenarios updated if needed
- [ ] Baseline updated if improved

---

## Summary

**Core principles**:
1. Measure first, optimize second
2. Establish baselines
3. Change one thing at a time
4. Consider trade-offs

**Key practices**:
- Sufficient sample sizes (100+ for latency)
- Report percentiles, not just means
- Use statistical significance tests
- Control environment
- Document everything

**Common mistakes to avoid**:
- Optimizing without measuring
- Ignoring regressions
- Testing in unrealistic conditions
- Not documenting trade-offs

**When in doubt**:
- Run more iterations
- Compare to baseline
- Check statistical significance
- Document uncertainties

---

## Further Reading

- [Performance Engineering](https://en.wikipedia.org/wiki/Performance_engineering)
- [Latency Numbers Every Programmer Should Know](https://gist.github.com/jboner/2841832)
- [How NOT to Measure Latency](https://www.youtube.com/watch?v=lJ8ydIuPFeU) (Gil Tene)
- [Benchmarking Crimes](https://www.cse.unsw.edu.au/~gernot/benchmarking-crimes.html)
- [Statistics for A/B Testing](https://www.evanmiller.org/ab-testing/)

---

**Remember**: Good benchmarking is about making informed decisions, not just collecting numbers.
