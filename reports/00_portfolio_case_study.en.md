**English** | [中文](00_portfolio_case_study.md)

# E-commerce Analytics Copilot: Portfolio Case Study

## Executive summary

This project uses the Olist public e-commerce dataset to build an auditable analytics foundation and consistent metric definitions before analyzing growth, category mix, regional fulfillment, seller performance, and customer retention. It then adds a controlled semantic-layer Copilot, an interactive dashboard, and a 50-question offline evaluation to measure natural-language analytics accuracy and safety.

## Key findings

| Topic | Finding | Business implication |
|---|---|---|
| Growth | Jan–Aug 2018 GMV grew 138.3% YoY; orders grew 137.3%; AOV changed 0.4% | Growth came primarily from order volume rather than higher basket size |
| Category | Health & beauty contributed 12.3% of net growth; the top five categories contributed 44.4% | Growth sources are concentrated, but dependence on any single category is limited |
| Geography | São Paulo contributed 43.4% of net growth; the top five states contributed 76.1% | Regional strategy should distinguish scale opportunities from fulfillment risks |
| Fulfillment | Alagoas had a 24.0% late-delivery rate; state late rate and review score had a -0.88 correlation | Prioritize high-volume regions and sellers with elevated late-delivery risk |
| Sellers | Top 10 sellers held 13.2% of GMV; HHI was 0.0036 | Platform dependence on top sellers is low; long-tail seller operations matter |
| Customers | Repeat purchase rate was 3.0%; weighted M1 retention was 0.48% | One-time buyers dominate, making the first 30 days the key retention window |
| Copilot | Answer accuracy was 97.8% vs. 24.4% for the keyword baseline; safety accuracy was 100% | A controlled semantic layer improves stability on the committed regression set |

![Monthly business performance](figures/business_overview_trends.png)

![Category growth contribution](figures/category_growth_contribution.png)

![Regional growth and fulfillment](figures/region_growth_service.png)

![Customer retention and cohorts](figures/customer_retention_segments.png)

## Recommendations

1. Protect supply and conversion in the highest-contributing categories while monitoring categories losing GMV share.
2. Prioritize fulfillment interventions with a combined score based on affected order volume, late-delivery rate, and low-review rate.
3. Treat the first 30 days after a customer's initial purchase as the primary experimentation window for category-specific repeat-purchase incentives.
4. Preserve the metric semantic layer, read-only SQL controls, and regression suite when integrating a real LLM; evaluate unseen questions separately.

## Technical and analytical design

```text
Olist CSV -> data quality checks -> DuckDB raw layer -> analytics views
          -> reusable SQL -> Python reports/charts -> interactive dashboard
          -> metric semantic layer -> controlled SQL -> 50-question evaluation
```

- Payments and reviews are aggregated to order grain before joining, preventing GMV inflation.
- GMV excludes freight; customers are identified with `customer_unique_id`; fulfillment metrics use comparable delivered orders.
- Growth analysis compares January–August 2017 and 2018, excluding sparse or incomplete periods.
- Copilot templates only emit `SELECT`/`WITH` statements; years and Top-N parameters are validated, and raw user text is never interpolated into SQL.

## Deliverables

- [Data quality findings](01_data_quality_findings.md)
- [Monthly business overview](02_business_overview.md)
- [Category growth contribution](03_category_growth.md)
- [Regional growth and fulfillment](04_region_fulfillment.md)
- [Seller performance](05_seller_performance.md)
- [Customer retention](06_customer_retention.md)
- [Copilot offline evaluation](07_copilot_evaluation.md)
- Interactive dashboard: `dashboard/index.html`

Detailed reports 01–07 are currently written in Chinese. This case study provides the English summary of their main evidence and conclusions.

## Limitations

- The dataset has no impressions, clicks, ad spend, margin, or experiment exposure; full-funnel conversion, ROI, and profit cannot be estimated.
- Fulfillment and review-score relationships are observational and do not establish causality.
- The Copilot is a controlled semantic-routing baseline, not a general-purpose LLM. Its accuracy is specific to the committed evaluation set.

Data source: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).
