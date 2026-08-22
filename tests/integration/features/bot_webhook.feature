# tests/behaviour/features/bot_webhook.feature
Feature: Bot webhook health and message delivery
  As an operator, I want the bot container to report healthy
  and correctly relay outbound messages through its webhook.

  Background:
    Given the docker compose stack is running

  Scenario: Bot reports healthy
    When I query the bot's health endpoint
    Then the response status is 200
    Then connect to bot using websocket and say hey

  Scenario Outline: Cron Job Tests
    When I query the bot's health endpoint
    Then Send message to bot "<message>" and expect "<criteria>"

    Examples:
    | message                                     | criteria  |
    | create a cron job schedule at 9 AM everyday to send a message via websockets on our chat |       t   |