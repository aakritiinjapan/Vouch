// Helper function to parse price from text
function parsePrice(text) {
  if (!text) return null;
  let cleaned = text.replace(/[^0-9.]/g, '');
  return cleaned ? parseFloat(cleaned) : null;
}

// Helper function to determine currency from price text
function getCurrency(text) {
  if (!text) return 'USD';
  return text.includes('$') ? 'USD' : 'USD';
}

// Extract all product items
let products = $('.grid .item').toArray().map(item => {
  let $item = $(item);
  
  // Extract name
  let name = $item.find('.item-title').text_sane();
  
  // Extract price - handle inconsistent structure
  let priceCurrentText = $item.find('.price-current').text_sane();
  let priceShipText = $item.find('.price-ship').text_sane();
  let priceWasText = $item.find('.price-was').text_sane();
  
  let priceValue, shippingValue, originalPriceValue;
  let currency = getCurrency(priceCurrentText || priceShipText);
  
  // If .price-current contains "Shipping", it's the shipping cost and actual price is in .price-ship
  if (priceCurrentText && priceCurrentText.toLowerCase().includes('shipping')) {
    shippingValue = parsePrice(priceCurrentText);
    priceValue = parsePrice(priceShipText);
    originalPriceValue = parsePrice(priceWasText);
  } else {
    // Otherwise .price-current is the selling price
    priceValue = parsePrice(priceCurrentText);
    shippingValue = null;
    originalPriceValue = parsePrice(priceWasText);
  }
  
  // Extract rating
  let ratingText = $item.find('.rating').text_sane();
  let rating = ratingText ? parseFloat(ratingText) : null;
  
  // Extract stock status
  let stockElement = $item.find('.stock');
  let in_stock = stockElement.hasClass('in');
  
  return {
    name: name || null,
    price: priceValue ? new Money(priceValue, currency) : null,
    original_price: originalPriceValue ? new Money(originalPriceValue, currency) : null,
    shipping: shippingValue ? new Money(shippingValue, currency) : null,
    rating: rating,
    in_stock: in_stock
  };
});

return {
  products: products
};