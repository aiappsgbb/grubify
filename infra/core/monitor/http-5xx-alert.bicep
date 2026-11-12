@description('Name of the metric alert rule. The SRE Agent response plan matches incidents on this name.')
param name string

@description('Resource ID of the container app to monitor')
param containerAppId string

@description('Number of HTTP 5xx responses within the window that fires the alert')
param threshold int = 5

param tags object = {}

// Minimal action group: the SRE Agent picks up the alert through Azure Monitor incident management
resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${name}'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'GrubifySRE'
    enabled: true
  }
}

resource http5xxAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: name
  location: 'global'
  tags: tags
  properties: {
    description: 'Grubify API is returning HTTP 5xx errors. Triggers an Azure SRE Agent investigation.'
    severity: 3
    enabled: true
    scopes: [
      containerAppId
    ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'http5xx'
          metricName: 'Requests'
          metricNamespace: 'microsoft.app/containerapps'
          operator: 'GreaterThan'
          threshold: threshold
          timeAggregation: 'Total'
          dimensions: [
            {
              name: 'statusCodeCategory'
              operator: 'Include'
              values: [
                '5xx'
              ]
            }
          ]
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

output name string = http5xxAlert.name
output id string = http5xxAlert.id
