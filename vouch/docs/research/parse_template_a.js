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
  
  // Extract current price
  let priceText = $item.find('.price-current').text_sane();
  let priceValue = parsePrice(priceText);
  let currency = getCurrency(priceText);
  
  // Extract original price (may not exist)
  let originalPriceText = $item.find('.price-was').text_sane();
  let originalPriceValue = parsePrice(originalPriceText);
  
  // Extract shipping cost
  let shippingText = $item.find('.price-ship').text_sane();
  let shippingValue = parsePrice(shippingText);
  
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