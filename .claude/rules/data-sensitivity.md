# Data Sensitivity Guidelines

## What NOT to Include in Prompts

### Never Include
- Customer PII (names, emails, addresses)
- API keys, tokens, passwords
- Financial account numbers
- Employee personal information (contact details, compensation, performance, health, or personal circumstances - not directory data, see Safe to Include)
- Confidential customer data or usage patterns
- Unpublished security vulnerabilities

### Use Caution With
- Specific revenue numbers (consider using ranges or %s)
- Unannounced product plans
- Ongoing legal matters
- Competitive intelligence sources
- Pricing details for specific deals

### Safe to Include
- Public product information
- General company strategy (high-level)
- Published metrics
- Team structure (roles, not personal details)
- Employee directory data: name, job title, department, manager, and Slack display name (internal workspace only, never in published content)
- Process documentation
- Technical architecture (non-security-sensitive)

## When Discussing Customers

- Use anonymized identifiers: "Customer A" or "Enterprise customer in fintech"
- Describe use cases generically when possible
- Don't include contract values or specific terms

## When Discussing Deals

- Use deal stage and approximate size range
- Don't include specific pricing offered
- Don't include customer objections verbatim

## When in Doubt

Ask: "Would I be comfortable if this appeared in a data breach?"
If no, don't include it.
