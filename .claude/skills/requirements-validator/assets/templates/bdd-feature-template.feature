# Template: BDD Feature File
# Copy and customize for each user story

Feature: [Feature Name]
  As a [actor]
  I want [capability]
  So that [benefit]

  Background:
    Given [common preconditions]

  # === HAPPY PATH (1-2 scenarios) ===
  
  @happy-path @critical @US-XXX
  Scenario: [Primary success case]
    Given [specific precondition with values]
    When [user action with parameters]
    Then [expected outcome with metrics]
    And [secondary outcome] within [time constraint]

  # === ERROR HANDLING (2-3 scenarios) ===

  @error-handling @US-XXX
  Scenario: [Validation error case]
    Given [precondition]
    When [action with invalid input]
    Then [error response with code and message]
    And [recovery option]

  @error-handling @US-XXX
  Scenario: [System error case]
    Given [precondition leading to system error]
    When [action that triggers error]
    Then [graceful error handling]
    And [error is logged with context]

  # === EDGE CASES (1-2 scenarios) ===

  @edge-case @US-XXX
  Scenario: [Boundary condition]
    Given [boundary precondition]
    When [action at boundary]
    Then [expected behavior at boundary]

  @edge-case @US-XXX
  Scenario: [Concurrent access / Race condition]
    Given [concurrent users/requests]
    When [simultaneous actions]
    Then [consistent behavior]

  # === SECURITY (if applicable) ===

  @security @US-XXX
  Scenario: [Authorization check]
    Given [user without permission]
    When [they attempt protected action]
    Then [access denied response]
    And [attempt is logged]

  # === DATA-DRIVEN EXAMPLES ===

  @validation @US-XXX
  Scenario Outline: Validate <field> input
    When user enters "<input>" in <field>
    Then they see "<result>"

    Examples:
      | field | input | result |
      | ... | ... | ... |
