# Runbook: High False Positive Rate

**Alert**: `HighFalsePositiveRate`
**Severity**: Warning
**Component**: Mistake Detector

## Symptoms

False positive rate exceeds 30% over the last hour, indicating detection accuracy problems.

## Impact

- User frustration with incorrect mistake detections
- Reduced trust in the system
- Wasted time reviewing and rejecting false positives
- Potential alert fatigue leading to ignoring real mistakes

## Investigation

### 1. Check rejection patterns

```bash
# View recent rejections
curl "http://localhost:8000/api/mistakes?status=rejected&limit=50"

# Check rejection reasons
psql -d blazing_buffalo -c "
  SELECT rejection_reason, COUNT(*) as count
  FROM mistake_corrections
  WHERE created_at > NOW() - INTERVAL '1 hour'
  AND status = 'rejected'
  GROUP BY rejection_reason
  ORDER BY count DESC;
"
```

### 2. Identify problematic patterns

```bash
# Find which detection patterns are causing false positives
psql -d blazing_buffalo -c "
  SELECT
    m.detection_pattern,
    COUNT(*) as total_detected,
    SUM(CASE WHEN mc.status = 'rejected' THEN 1 ELSE 0 END) as rejected,
    ROUND(100.0 * SUM(CASE WHEN mc.status = 'rejected' THEN 1 ELSE 0 END) / COUNT(*), 2) as rejection_rate
  FROM mistakes m
  LEFT JOIN mistake_corrections mc ON m.id = mc.mistake_id
  WHERE m.created_at > NOW() - INTERVAL '1 hour'
  GROUP BY m.detection_pattern
  HAVING SUM(CASE WHEN mc.status = 'rejected' THEN 1 ELSE 0 END) > 5
  ORDER BY rejection_rate DESC;
"
```

### 3. Review recent pattern changes

```bash
# Check if new patterns were recently deployed
git log --since="24 hours ago" --oneline -- lib/mistake_patterns/

# Review pattern confidence thresholds
grep -r "confidence_threshold" lib/mistake_patterns/
```

## Resolution

### Immediate Actions

1. **Lower confidence threshold for problematic patterns**:
   ```python
   # In lib/mistake_patterns/{pattern}.py
   CONFIDENCE_THRESHOLD = 0.8  # Increase from 0.6 to reduce false positives
   ```

2. **Temporarily disable high-FP patterns**:
   ```bash
   curl -X POST "http://localhost:8000/api/patterns/{pattern_id}/disable" \
     -H "Content-Type: application/json" \
     -d '{"reason": "High false positive rate", "temporary": true}'
   ```

### Long-term Fixes

1. **Retrain pattern classifiers**:
   ```bash
   # Export recent rejections for training
   python scripts/export_training_data.py --rejected --since="7 days"

   # Retrain models
   python scripts/train_classifiers.py --pattern={pattern_id} --data=rejected_samples.json

   # Validate before deployment
   python scripts/validate_classifier.py --pattern={pattern_id} --test-set=validation.json
   ```

2. **Refine detection rules**:
   - Add negative examples to pattern matching
   - Increase specificity of regex/AST patterns
   - Add context-aware filtering

3. **Implement feedback loop**:
   ```bash
   # Enable auto-tuning based on rejection rates
   curl -X POST "http://localhost:8000/api/settings/auto-tune" \
     -H "Content-Type: application/json" \
     -d '{"enabled": true, "target_rejection_rate": 0.15}'
   ```

## Prevention

- Monitor rejection rates per pattern continuously
- A/B test new patterns before full deployment
- Implement staged rollouts for pattern changes
- Collect diverse training examples
- Regular pattern effectiveness reviews
- User feedback integration into training pipeline

## Escalation

If false positive rate remains >30% after 2 hours:
- Notify: @ml-team, @engineering-oncall
- Channel: #blazing-buffalo-accuracy
- Include: affected patterns, rejection analysis, attempted fixes
