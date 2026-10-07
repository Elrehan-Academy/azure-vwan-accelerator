using './main.bicep'

// Example configuration. Review names and address ranges before deployment.
param virtualWanName = 'vwan-example'
param virtualWanLocation = 'westeurope'
param hubName = 'vhub-example-weu'
param hubLocation = 'westeurope'
param hubAddressPrefix = '10.250.0.0/24'

param tags = {
  environment: 'example'
  owner: 'replace-with-service-owner'
  cost_center: 'replace-with-cost-centre'
}
