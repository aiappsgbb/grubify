param name string
param location string = resourceGroup().location
param tags object = {}

@description('Resource ID of the Log Analytics workspace backing Application Insights')
param logAnalyticsWorkspaceId string

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: name
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    Request_Source: 'IbizaAIExtension'
    WorkspaceResourceId: logAnalyticsWorkspaceId
  }
}

output id string = applicationInsights.id
output name string = applicationInsights.name
output appId string = applicationInsights.properties.AppId
#disable-next-line outputs-should-not-contain-secrets
output connectionString string = applicationInsights.properties.ConnectionString
