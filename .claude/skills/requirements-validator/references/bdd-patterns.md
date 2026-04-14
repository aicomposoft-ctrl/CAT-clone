# BDD Patterns and Gherkin Templates

## Scenario Coverage Requirements

For each user story, generate:

| Type | Count | Purpose |
|------|-------|---------|
| Happy path | 1-2 | Primary success flows |
| Error handling | 2-3 | Validation, network, server errors |
| Edge cases | 1-2 | Boundaries, nulls, concurrency |
| Security | 0-2 | Auth, injection (if applicable) |

## Feature Template

```gherkin
Feature: [Feature Name from User Story]
  As a [actor from user story]
  I want [action from user story]
  So that [benefit from user story]

  Background:
    Given [common preconditions]

  @happy-path @critical
  Scenario: [Primary success case]
    Given [specific precondition]
    When [user action]
    Then [expected outcome with metrics]

  @error-handling
  Scenario: [Error case name]
    Given [precondition leading to error]
    When [action that triggers error]
    Then [error handling behavior]

  @edge-case
  Scenario: [Edge case name]
    Given [boundary condition]
    When [action at boundary]
    Then [expected behavior]
```

## Common Scenario Patterns

### Authentication

```gherkin
@happy-path
Scenario: Successful login
  Given a registered user with email "user@example.com"
  When they enter valid credentials
  And click "Login"
  Then they are redirected to the dashboard within 2s
  And a session is created expiring in 24h

@error-handling
Scenario: Invalid credentials
  Given a registered user
  When they enter incorrect password
  Then they see error "Invalid email or password"
  And no session is created
  And login attempts are logged

@security
Scenario: Account lockout after failed attempts
  Given a registered user
  When they fail login 5 times within 15 minutes
  Then the account is locked for 30 minutes
  And they receive a security alert email
```

### CRUD Operations

```gherkin
@happy-path
Scenario: Create resource
  Given an authenticated user with create permission
  When they submit valid resource data
  Then the resource is created
  And they receive 201 Created with resource ID
  And the response time is <500ms

@error-handling
Scenario: Create with invalid data
  Given an authenticated user
  When they submit resource with missing required field "name"
  Then they receive 400 Bad Request
  And error message specifies "name is required"

@edge-case
Scenario: Create duplicate resource
  Given an existing resource with name "Test"
  When user creates another resource with name "Test"
  Then they receive 409 Conflict
  And error message specifies the duplicate field
```

### Search/Filter

```gherkin
@happy-path
Scenario: Search returns results
  Given 100 products in the database
  And 15 products match "laptop"
  When user searches for "laptop"
  Then they see 15 results within 500ms
  And results are paginated with 10 per page

@edge-case
Scenario: Search with no results
  Given 100 products in the database
  When user searches for "xyznonexistent123"
  Then they see "No results found" message
  And search suggestions are displayed

@edge-case
Scenario: Search with special characters
  Given products with names containing quotes
  When user searches for "15\" laptop"
  Then the search handles the quote correctly
  And returns matching products
```

### Async Operations

```gherkin
@happy-path
Scenario: Async job completion
  Given a user submits a report generation request
  Then they receive 202 Accepted with job ID
  And job status is "processing"
  When the job completes (within 60s)
  Then job status changes to "completed"
  And download link is available

@error-handling
Scenario: Async job timeout
  Given a report generation job
  When processing exceeds 5 minutes
  Then job status changes to "failed"
  And user is notified via email
  And partial results are preserved
```

## Tags Reference

| Tag | Purpose |
|-----|---------|
| @critical | Must pass for release |
| @happy-path | Primary success flows |
| @error-handling | Error conditions |
| @edge-case | Boundary conditions |
| @security | Security-related |
| @performance | Has timing requirements |
| @smoke | Quick sanity check |
| @regression | Full regression suite |

## Data Table Patterns

```gherkin
Scenario Outline: Validate input fields
  When user enters <input> in the <field> field
  Then they see <result>

  Examples:
    | field    | input              | result           |
    | email    | valid@email.com    | field is valid   |
    | email    | invalid-email      | "Invalid email"  |
    | password | short              | "Min 8 chars"    |
    | password | ValidPass123!      | field is valid   |
```

## Traceability

Each scenario should link to its source requirement:

```gherkin
@US-001 @AC-001
Scenario: User login success
  ...
```

This enables bidirectional traceability between requirements and tests.
