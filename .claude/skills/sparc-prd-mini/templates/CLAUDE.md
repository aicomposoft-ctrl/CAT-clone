# {PROJECT_NAME}

## Project Documentation

This project follows SPARC methodology. Read these documents in order:

### 1. Specification (WHAT to build)
- `Specification.md` - User stories, acceptance criteria, requirements
- `PRD.md` - Product context, personas, success metrics

### 2. Pseudocode (HOW it works)
- `Pseudocode.md` - Algorithms, data structures, state transitions

### 3. Architecture (SYSTEM design)
- `Architecture.md` - Components, tech stack, integrations

### 4. Refinement (QUALITY)
- `Refinement.md` - Edge cases, tests, optimizations

### 5. Completion (DEPLOY)
- `Completion.md` - CI/CD, monitoring, runbooks

## Implementation Rules

### Code Standards
- Match pseudocode specifications exactly
- Follow naming conventions established in Architecture.md
- Add tests for all new functionality
- Document public APIs

### Priority Order
1. Implement "Must" requirements first (see Specification.md)
2. Then "Should" requirements
3. "Could" requirements only if time permits

### Error Handling
- Use error codes defined in Refinement.md
- Log with structured format from Completion.md
- Always validate inputs before processing

### Testing
- Write tests BEFORE implementation (TDD)
- Cover all acceptance criteria
- Include edge cases from Refinement.md

## File Structure

```
src/
├── api/          # HTTP handlers
├── services/     # Business logic
├── repositories/ # Data access
├── models/       # Domain entities
├── utils/        # Shared utilities
└── config/       # Configuration
```

## Quick Reference

### Key Entities
<!-- Add main domain entities here -->

### API Endpoints
<!-- Add main API endpoints here -->

### Environment Variables
```
DATABASE_URL=
API_KEY=
```

## Getting Started

```bash
# Install dependencies
npm install  # or pip install -r requirements.txt

# Run tests
npm test

# Start development
npm run dev
```

## Notes for AI Assistants

- When implementing features, always check Specification.md first
- Cross-reference Pseudocode.md for algorithm details
- Verify technology choices against Architecture.md
- Check Refinement.md for edge cases before completing
- Follow deployment checklist in Completion.md
