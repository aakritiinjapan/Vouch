// Helper function to parse price from text
function parsePrice(text) {
  if (!text) return null;
  // Remove currency symbols and text, keep only numbers and decimal point
  let cleaned = text.replace(/[^0-9.]/g, '');
  // Handle multiple decimal points by keeping only the last one
  let parts = cleaned.split('.');
  if (parts.length > 2) {
    cleaned = parts.slice(0, -1).join('') + '.' + parts[parts.length - 1];
  }
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
  
  let name = $item.find('.item-title').text_sane();
  
  // Extract current selling price (the price customer pays)
  let priceText = $item.find('.price-current').text_sane();
  let priceValue = parsePrice(priceText);
  let currency = getCurrency(priceText);
  
  // Extract original/crossed-out price
  let originalPriceText = $item.find('.price-was').text_sane();
  let originalPriceValue = parsePrice(originalPriceText);
  
  // Extract shipping cost (separate from product price)
  let shippingText = $item.find('.price-ship').text_sane();
  let shippingValue = parsePrice(shippingText);
  
  let ratingText = $item.find('.rating').text_sane();
  let rating = ratingText ? parseFloat(ratingText) : null;
  
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