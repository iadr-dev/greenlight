Feature: Boundaries

  @R-1.1
  Scenario Outline: Shipping by weight
    Given a parcel of <kg> kg
    When shipping is quoted
    Then the fee is <fee>

    @partition-light
    Examples: light parcels
      | kg | fee |
      | 0  | 5   |
      | 1  | 5   |

    @partition-heavy
    Examples: heavy parcels
      | kg | fee |
      | 20 | 15  |
      | 21 | 30  |
