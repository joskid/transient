Feature: Command line interface
  In order to use transient, users can access the command line interface.

Scenario: Invalid flag
    Given a transient vm
      And a name "test-vm"
      And a disk image "generic/alpine38:v3.0.2"
      And a flag "-ssh-foobar"
     When the transient command is run
     Then the return code is 2
      And stderr contains "Error: no such option: -ssh-foobar"

Scenario: Missing name
    Given a transient vm
      And a disk image "generic/alpine38:v3.0.2"
     When the transient command is run
     Then the return code is 2
      And stderr contains "Error: Missing option '-name'."